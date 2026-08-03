from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import json
import logging
import re

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from sports_predictor.artifacts import verify_artifact_manifest
from sports_predictor.release_registry import APP_VERSION, build_release_evidence
from sports_predictor.cloud_auth import (
    AuthenticationGateMiddleware,
    LOGIN_LIMITER,
    clear_session,
    client_key,
    establish_session,
    verify_password,
)
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import (
    database_summary,
    init_database,
    persist_odds_rows,
    predictions_for_date,
    recent_predictions,
    recent_sync_runs,
    recent_backfill_jobs,
    recent_data_quality_issues,
    latest_benchmark_run,
    latest_model_decision,
    latest_shadow_cycle,
    list_models,
    list_releases,
    model_status_history,
    recent_shadow_predictions,
    record_prediction,
    record_model_decision,
    record_shadow_prediction,
    register_model,
    register_release,
    set_model_status,
    shadow_summary,
)
from sports_predictor.betting import analyze_market, analyze_three_way, analyze_two_way
from sports_predictor.football import FootballPredictor
from sports_predictor.tennis import TennisPredictor
from sports_predictor.data_sources.the_odds_api import (
    OddsApiClient,
    OddsApiConfig,
    OddsApiError,
    OddsApiNotConfigured,
)
from sports_predictor.identity import football_model_name, normalize_identity
from sports_predictor.odds_data import bookmaker_h2h_markets, consensus_h2h, normalize_odds_payload
from sports_predictor.market_benchmark import benchmark_summary
from sports_predictor.champion_challenger import build_model_decision
from sports_predictor.control_center import build_control_center
from sports_predictor.shadow_mode import shadow_horizon

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DAILY_SLATE = ROOT / "data" / "daily_slate"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SPORT_KEY_RE = re.compile(r"^[a-z0-9_\-]+$")
ODDS_BOOKMAKERS = ("winamax_fr", "betclic_fr", "unibet_fr", "pmu_fr", "netbet_fr", "pinnacle")
SPORT_LEAGUE_MAP = {"soccer_epl": "E0"}
SETTINGS = CloudSettings.from_env(ROOT)
STARTUP_STATE: dict[str, str | None] = {"database_error": None, "model_error": None}
LOGGER = logging.getLogger("sports_prediction_lab.startup")


def _model_freshness(*, data_cutoff: Any, as_of: Any) -> dict[str, Any]:
    cutoff = pd.to_datetime(data_cutoff, utc=True, errors="coerce")
    reference = pd.to_datetime(as_of, utc=True, errors="coerce")
    if pd.isna(cutoff) or pd.isna(reference):
        return {"status": "unknown", "age_days": None, "stale": True}
    age_days = max(0, int((reference - cutoff).total_seconds() // 86400))
    return {
        "status": "degraded_stale" if age_days > SETTINGS.model_max_age_days else "current",
        "age_days": age_days,
        "stale": age_days > SETTINGS.model_max_age_days,
        "maximum_age_days": SETTINGS.model_max_age_days,
        "data_cutoff": cutoff.isoformat(),
    }


def _apply_market_veto(analysis: dict[str, Any], *, reason: str) -> dict[str, Any]:
    analysis = json.loads(json.dumps(analysis))
    analysis["shortlist"] = []
    for selection in analysis.get("selections", []) or []:
        if selection.get("status") in {"candidat", "candidat recherche", "surveillance"}:
            selection["status"] = "abstention"
        reasons = list(selection.get("reasons") or [])
        if reason not in reasons:
            reasons.append(reason)
        selection["reasons"] = reasons
    analysis["operational_veto"] = reason
    return analysis


def initialize_runtime() -> None:
    try:
        init_database(SETTINGS)
        register_release(build_release_evidence(ROOT, version=APP_VERSION), status="running")
        STARTUP_STATE["database_error"] = None
    except Exception as exc:  # readiness reports the failure without exposing credentials
        STARTUP_STATE["database_error"] = type(exc).__name__
        LOGGER.error("database startup failed error_type=%s", type(exc).__name__)
    try:
        loaded = resources()
        STARTUP_STATE["model_error"] = None
        manifest_files = {item.get("name"): item.get("sha256") for item in loaded["artifact_manifest"].get("files", [])}
        football_cutoff = pd.to_datetime(loaded["football"]["date"], utc=True).max()
        football_freshness = _model_freshness(data_cutoff=football_cutoff, as_of=datetime.now(ZoneInfo("UTC")))
        register_model(
            model_id="football-1n2-shadow", sport="football", version=loaded["football_model_version"],
            status="degraded" if football_freshness["stale"] else "shadow",
            trained_until=football_cutoff,
            dataset_hash=((loaded.get("fresh_rebuild") or {}).get("dataset") or {}).get("sha256") or manifest_files.get("football_model.joblib"),
            metrics={**(loaded["metrics"].get("football") or {}), "freshness": football_freshness},
            update_status=False,
        )
        register_model(
            model_id="market-winamax-baseline", sport="football", version="market-v1", status="shadow",
            trained_until=None, dataset_hash=None, metrics={"role": "bookmaker baseline", "betting_enabled": False},
            update_status=False,
        )
        register_model(
            model_id="market-consensus-baseline", sport="football", version="consensus-v1", status="shadow",
            trained_until=None, dataset_hash=None, metrics={"role": "devigged consensus baseline", "betting_enabled": False},
            update_status=False,
        )
        register_model(
            model_id="football-consensus-blend", sport="football", version="blend-50-v1", status="shadow",
            trained_until=football_cutoff, dataset_hash=((loaded.get("fresh_rebuild") or {}).get("dataset") or {}).get("sha256"),
            metrics={"role": "fixed 50/50 challenger", "automatic_promotion": False}, update_status=False,
        )
        register_model(
            model_id="tennis-elo-experimental", sport="tennis", version=SETTINGS.model_version, status="experimental",
            trained_until=pd.to_datetime(loaded["tennis"]["date"], utc=True).max(),
            dataset_hash=manifest_files.get("tennis_model.joblib"), metrics=loaded["metrics"].get("tennis"),
            update_status=False,
        )
    except Exception as exc:
        STARTUP_STATE["model_error"] = type(exc).__name__
        LOGGER.error("model startup failed error_type=%s", type(exc).__name__)
    LOGGER.info(
        "startup readiness version=%s database_error=%s model_error=%s config_issues=%s",
        APP_VERSION,
        STARTUP_STATE.get("database_error") or "none",
        STARTUP_STATE.get("model_error") or "none",
        ",".join(SETTINGS.readiness_issues()) or "none",
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_runtime()
    yield


app = FastAPI(
    title="Sports Prediction Lab V4.2 Coverage-Aware Evidence Planning",
    version=APP_VERSION,
    description="Cloud-first data-reliability edition with explicit coverage denominators, zero-credit evidence recomputation, bookmaker matrices and leakage-safe quality gates.",
    lifespan=lifespan,
)
app.add_middleware(AuthenticationGateMiddleware, settings=SETTINGS)
app.add_middleware(
    SessionMiddleware,
    secret_key=SETTINGS.session_secret or "missing-production-session-secret",
    session_cookie="sports_prediction_session",
    max_age=60 * 60 * 12,
    same_site="strict",
    https_only=SETTINGS.cookie_secure,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith(("/docs", "/redoc")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
    return response


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class FootballRequest(BaseModel):
    home_team: str = Field(min_length=1, max_length=120)
    away_team: str = Field(min_length=1, max_length=120)
    date: str | None = None
    league: str = Field(default="E0", min_length=1, max_length=20)
    winamax_home_odds: float | None = Field(default=None, gt=1.0, le=1000)
    winamax_draw_odds: float | None = Field(default=None, gt=1.0, le=1000)
    winamax_away_odds: float | None = Field(default=None, gt=1.0, le=1000)
    odds_observed_at: str | None = Field(default=None, max_length=64)

    @field_validator("away_team")
    @classmethod
    def teams_must_differ(cls, value: str, info):
        if info.data.get("home_team") == value:
            raise ValueError("home_team and away_team must differ")
        return value

    @model_validator(mode="after")
    def complete_odds_market(self):
        odds = [self.winamax_home_odds, self.winamax_draw_odds, self.winamax_away_odds]
        if any(x is not None for x in odds) and not all(x is not None for x in odds):
            raise ValueError("Provide all three Winamax 1N2 odds or none")
        return self


class TennisRequest(BaseModel):
    player_1: str = Field(min_length=1, max_length=120)
    player_2: str = Field(min_length=1, max_length=120)
    surface: str = "hard"
    date: str | None = None
    tournament_level: str = "A"
    best_of: int = Field(default=3, ge=3, le=5)
    winamax_player_1_odds: float | None = Field(default=None, gt=1.0, le=1000)
    winamax_player_2_odds: float | None = Field(default=None, gt=1.0, le=1000)
    odds_observed_at: str | None = Field(default=None, max_length=64)

    @field_validator("surface")
    @classmethod
    def valid_surface(cls, value: str):
        value = value.lower()
        if value not in {"hard", "clay", "grass", "carpet"}:
            raise ValueError("Unsupported surface")
        return value

    @field_validator("best_of")
    @classmethod
    def valid_best_of(cls, value: int):
        if value not in {3, 5}:
            raise ValueError("best_of must be 3 or 5")
        return value

    @field_validator("player_2")
    @classmethod
    def players_must_differ(cls, value: str, info):
        if info.data.get("player_1") == value:
            raise ValueError("player_1 and player_2 must differ")
        return value

    @model_validator(mode="after")
    def complete_odds_market(self):
        odds = [self.winamax_player_1_odds, self.winamax_player_2_odds]
        if any(x is not None for x in odds) and not all(x is not None for x in odds):
            raise ValueError("Provide both Winamax match-winner odds or none")
        return self


class ModelStatusRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    new_status: str = Field(pattern=r"^(shadow|active|degraded|retired)$")
    reason: str = Field(min_length=3, max_length=500)
    actor: str = Field(default="admin", min_length=1, max_length=120)


class HistoricalEstimateRequest(BaseModel):
    snapshot_count: int = Field(ge=0, le=100000)
    markets: list[str] = Field(default_factory=lambda: ["h2h"], min_length=1, max_length=20)
    bookmakers: list[str] = Field(default_factory=lambda: list(ODDS_BOOKMAKERS), min_length=1, max_length=50)
    historical: bool = True

    @field_validator("markets", "bookmakers")
    @classmethod
    def valid_tokens(cls, values: list[str]):
        if any(not SPORT_KEY_RE.fullmatch(str(value)) for value in values):
            raise ValueError("Only lowercase API tokens are accepted")
        return values


@lru_cache(maxsize=1)
def resources() -> dict[str, Any]:
    active_football = ROOT / "data/real/football_active.csv"
    football_source = active_football if active_football.exists() else ROOT / "data/real_snapshot/football_epl_2023_24_snapshot.csv"
    football = pd.read_csv(football_source)
    tennis = pd.read_csv(ROOT / "data/real_snapshot/tennis_atp_2025_snapshot.csv")
    football_model = FootballPredictor()
    tennis_model = TennisPredictor()
    artifact_dir = ROOT / "artifacts"
    football_path = artifact_dir / "football_model.joblib"
    tennis_path = artifact_dir / "tennis_model.joblib"
    manifest_path = artifact_dir / "artifact_manifest.json"
    if not football_path.exists() or not tennis_path.exists() or not manifest_path.exists():
        raise RuntimeError("Missing model artifacts or manifest. Run python scripts/train_snapshot.py")
    artifact_manifest = verify_artifact_manifest(artifact_dir, manifest_path)
    football_model.load(football_path)
    tennis_model.load(tennis_path)
    metrics_path = artifact_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    provenance = json.loads((ROOT / "data/real_snapshot/PROVENANCE.json").read_text(encoding="utf-8"))
    backtest_path = ROOT / "artifacts/backtest_snapshot.json"
    backtest = json.loads(backtest_path.read_text(encoding="utf-8")) if backtest_path.exists() else {}
    fresh_rebuild_path = artifact_dir / "fresh_rebuild_report.json"
    fresh_rebuild = json.loads(fresh_rebuild_path.read_text(encoding="utf-8")) if fresh_rebuild_path.exists() else None
    football_model_version = (
        f"{fresh_rebuild.get('version', APP_VERSION)}-fresh"
        if fresh_rebuild and fresh_rebuild.get("promoted")
        else "3.3.0-snapshot"
    )
    return {
        "football": football,
        "tennis": tennis,
        "football_model": football_model,
        "tennis_model": tennis_model,
        "metrics": metrics,
        "backtest": backtest,
        "provenance": provenance,
        "artifact_manifest": artifact_manifest,
        "football_data_source": str(football_source.relative_to(ROOT)),
        "fresh_rebuild": fresh_rebuild,
        "football_model_version": football_model_version,
    }


@lru_cache(maxsize=1)
def odds_client() -> OddsApiClient:
    return OddsApiClient(OddsApiConfig.from_env(root=ROOT))


initialize_runtime()


def _iso(value: Any) -> str | None:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.isoformat().replace("+00:00", "Z")


def _persist_odds_response(rows: pd.DataFrame, response: Any, *, sport_key: str, job_name: str) -> dict[str, int]:
    try:
        return persist_odds_rows(
            rows,
            fetched_at=response.fetched_at,
            quota_remaining=response.quota.remaining,
            quota_last_cost=response.quota.last_cost,
            job_name=job_name,
            sport_key=sport_key,
        )
    except Exception as exc:
        STARTUP_STATE["database_error"] = type(exc).__name__
        raise HTTPException(status_code=503, detail="Odds were received but could not be persisted safely") from exc


def _record_prediction_payload(payload: dict[str, Any], *, provider_event_id: str | None = None) -> int:
    analysis = payload.get("market_analysis")
    decision = "candidat recherche" if analysis and analysis.get("shortlist") else "abstention"
    try:
        return record_prediction(
            sport=str(payload["sport"]),
            model_version=str(payload.get("model_version") or SETTINGS.model_version),
            fixture=payload["fixture"],
            probabilities=payload["probabilities"],
            market_analysis=analysis,
            decision=decision,
            provider_event_id=provider_event_id,
        )
    except Exception as exc:
        STARTUP_STATE["database_error"] = type(exc).__name__
        raise HTTPException(status_code=503, detail="Prediction computed but audit persistence failed") from exc


def _record_shadow_payload(
    payload: dict[str, Any], *, provider_event_id: str, sport_key: str, commence_time: Any,
    odds_observed_at: Any | None, decision: str, source: str, model_id: str, data_cutoff: Any,
) -> dict[str, Any]:
    if not SETTINGS.shadow_enabled:
        return {"created": False, "disabled": True}
    try:
        return record_shadow_prediction(
            provider_event_id=provider_event_id, sport_key=sport_key, sport=str(payload["sport"]),
            model_id=model_id, model_version=str(payload.get("model_version") or SETTINGS.model_version), fixture=payload["fixture"],
            probabilities=payload["probabilities"], market_analysis=payload.get("market_analysis"),
            decision=decision, source=source, prediction_created_at=datetime.now(ZoneInfo("UTC")),
            commence_time=commence_time, odds_observed_at=odds_observed_at, data_cutoff=data_cutoff,
        )
    except Exception as exc:
        STARTUP_STATE["database_error"] = type(exc).__name__
        raise HTTPException(status_code=503, detail="Shadow prediction computed but immutable audit persistence failed") from exc


def _contender_payload(base: dict[str, Any], *, probabilities: dict[str, float], model_version: str) -> dict[str, Any]:
    payload = json.loads(json.dumps(base))
    payload["probabilities"] = {
        "home": float(probabilities["home"]),
        "draw": float(probabilities["draw"]),
        "away": float(probabilities["away"]),
    }
    payload["model_version"] = model_version
    payload["market_analysis"] = None
    payload["contender_only"] = True
    return payload


def _record_football_contenders(
    *, prediction: dict[str, Any], event_id: str, sport_key: str, commence_time: Any,
    observed_at: Any, data_cutoff: Any, api_home: str, api_away: str,
    winamax: dict[str, Any], consensus: dict[str, Any] | None,
) -> dict[str, Any]:
    records: dict[str, Any] = {}
    market_probabilities = {
        "home": float(winamax["probabilities"][api_home]),
        "draw": float(winamax["probabilities"]["Draw"]),
        "away": float(winamax["probabilities"][api_away]),
    }
    records["winamax"] = _record_shadow_payload(
        _contender_payload(prediction, probabilities=market_probabilities, model_version="market-v1"),
        provider_event_id=event_id, sport_key=sport_key, commence_time=commence_time,
        odds_observed_at=observed_at, decision="benchmark_only", source="the_odds_api_current",
        model_id="market-winamax-baseline", data_cutoff=data_cutoff,
    )
    if consensus:
        consensus_probabilities = {
            "home": float(consensus["probabilities"][api_home]),
            "draw": float(consensus["probabilities"]["Draw"]),
            "away": float(consensus["probabilities"][api_away]),
        }
        records["consensus"] = _record_shadow_payload(
            _contender_payload(prediction, probabilities=consensus_probabilities, model_version="consensus-v1"),
            provider_event_id=event_id, sport_key=sport_key, commence_time=commence_time,
            odds_observed_at=observed_at, decision="benchmark_only", source="the_odds_api_current",
            model_id="market-consensus-baseline", data_cutoff=data_cutoff,
        )
        model = prediction["probabilities"]
        blend_probabilities = {
            key: 0.5 * float(model[key]) + 0.5 * float(consensus_probabilities[key])
            for key in ("home", "draw", "away")
        }
        records["blend"] = _record_shadow_payload(
            _contender_payload(prediction, probabilities=blend_probabilities, model_version="blend-50-v1"),
            provider_event_id=event_id, sport_key=sport_key, commence_time=commence_time,
            odds_observed_at=observed_at, decision="benchmark_only", source="the_odds_api_current",
            model_id="football-consensus-blend", data_cutoff=data_cutoff,
        )
    return records


def _football_odds_slate(sport_key: str, league: str, *, force_refresh: bool = False) -> dict[str, Any]:
    r = resources()
    history = r["football"]
    league_history = history[history["league"].astype(str) == league]
    if league_history.empty:
        raise HTTPException(status_code=422, detail=f"Unknown bundled league: {league}")
    model_teams = set(league_history["home_team"]) | set(league_history["away_team"])
    try:
        response = odds_client().current_odds(
            sport_key,
            markets=("h2h",),
            bookmakers=ODDS_BOOKMAKERS,
            force_refresh=force_refresh,
        )
    except OddsApiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OddsApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    rows = normalize_odds_payload(response.payload)
    storage = _persist_odds_response(rows, response, sport_key=sport_key, job_name="football_live_slate")
    markets = bookmaker_h2h_markets(rows)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for market in markets:
        grouped.setdefault(str(market["event_id"]), []).append(market)

    provider_event_count = len(grouped)
    grouped_items = list(grouped.items())[:SETTINGS.shadow_max_events]
    now = pd.Timestamp.now(tz="UTC")
    funnel: dict[str, int] = {
        "provider_events": provider_event_count,
        "events_considered": len(grouped_items),
        "events_truncated": max(0, provider_event_count - len(grouped_items)),
        "in_play": 0,
        "outside_shadow_horizon": 0,
        "identity_uncovered": 0,
        "winamax_missing": 0,
        "market_incomplete": 0,
        "model_stale_veto": 0,
        "no_robust_edge": 0,
        "research_candidates": 0,
        "shadow_created": 0,
        "shadow_reused": 0,
    }
    events: list[dict[str, Any]] = []
    for event_id, event_markets in grouped_items:
        first = event_markets[0]
        api_home = str(first["home_team"])
        api_away = str(first["away_team"])
        home = football_model_name(api_home)
        away = football_model_name(api_away)
        winamax = next((m for m in event_markets if m["bookmaker_key"] == "winamax_fr"), None)
        consensus = consensus_h2h(event_markets, exclude=("winamax_fr",))
        commence_ts = pd.to_datetime(first["commence_time"], utc=True, errors="coerce")
        in_play = bool(not pd.isna(commence_ts) and commence_ts <= now)
        horizon = None if pd.isna(commence_ts) else shadow_horizon(prediction_created_at=now, commence_time=commence_ts)
        base = {
            "event_id": event_id,
            "sport_key": sport_key,
            "commence_time": _iso(first["commence_time"]),
            "api_home_team": api_home,
            "api_away_team": api_away,
            "model_home_team": home,
            "model_away_team": away,
            "winamax_available": winamax is not None,
            "in_play": in_play,
            "shadow_horizon": horizon,
            "consensus": consensus,
            "decision": "abstention",
            "reasons": [],
        }
        if in_play:
            funnel["in_play"] += 1
            base["reasons"].append("match commencé : modèle pré-match désactivé")
            events.append(base)
            continue
        if horizon is None:
            funnel["outside_shadow_horizon"] += 1
            base["reasons"].append("hors des jalons shadow T−24 h, T−6 h, T−1 h et pré-clôture")
            events.append(base)
            continue
        if home not in model_teams or away not in model_teams:
            funnel["identity_uncovered"] += 1
            base["reasons"].append("identité non couverte par le modèle embarqué")
            events.append(base)
            continue
        prediction_date = pd.to_datetime(first["commence_time"], utc=True).date().isoformat()
        prediction = _football_prediction(FootballRequest(home_team=home, away_team=away, date=prediction_date, league=league))
        model_probs = [prediction["probabilities"]["home"], prediction["probabilities"]["draw"], prediction["probabilities"]["away"]]
        base["model"] = prediction
        if winamax is None:
            funnel["winamax_missing"] += 1
            base["reasons"].append("cotes Winamax absentes du snapshot fournisseur")
            base["shadow_record"] = _record_shadow_payload(
                prediction, provider_event_id=event_id, sport_key=sport_key, commence_time=first["commence_time"],
                odds_observed_at=None, decision="abstention", source="the_odds_api_current",
                model_id="football-1n2-shadow", data_cutoff=pd.to_datetime(history["date"], utc=True).max(),
            )
            events.append(base)
            continue
        labels = [api_home, "Draw", api_away]
        if any(label not in winamax["odds"] for label in labels):
            funnel["market_incomplete"] += 1
            base["reasons"].append("marché Winamax incomplet")
            base["shadow_record"] = _record_shadow_payload(
                prediction, provider_event_id=event_id, sport_key=sport_key, commence_time=first["commence_time"],
                odds_observed_at=_iso(winamax["last_update"]), decision="abstention", source="the_odds_api_current",
                model_id="football-1n2-shadow", data_cutoff=pd.to_datetime(history["date"], utc=True).max(),
            )
            events.append(base)
            continue
        analysis = analyze_market(
            labels=[home, "Match nul", away],
            model_probabilities=model_probs,
            decimal_odds=[winamax["odds"][api_home], winamax["odds"]["Draw"], winamax["odds"][api_away]],
            bookmaker="Winamax via The Odds API",
            market_type="1N2",
            observed_at=_iso(winamax["last_update"]),
            calibrated=True,
        ).to_dict()
        if prediction.get("model_freshness", {}).get("stale"):
            funnel["model_stale_veto"] += 1
            analysis = _apply_market_veto(analysis, reason="modèle trop ancien pour une sélection opérationnelle")
            base["reasons"].append("modèle trop ancien : shadow mode uniquement")
        base["winamax"] = {
            "odds": winamax["odds"],
            "probabilities": winamax["probabilities"],
            "overround": winamax["overround"],
            "last_update": _iso(winamax["last_update"]),
        }
        base["market_analysis"] = analysis
        prediction["market_analysis"] = analysis
        base["decision"] = "candidat recherche" if analysis["shortlist"] else "abstention"
        if analysis["shortlist"]:
            funnel["research_candidates"] += 1
        else:
            funnel["no_robust_edge"] += 1
            reasons = sorted({reason for selection in analysis["selections"] for reason in selection["reasons"]})
            base["reasons"].extend(reasons or ["aucun edge robuste"])
        data_cutoff = pd.to_datetime(history["date"], utc=True).max()
        base["shadow_record"] = _record_shadow_payload(
            prediction, provider_event_id=event_id, sport_key=sport_key, commence_time=first["commence_time"],
            odds_observed_at=_iso(winamax["last_update"]), decision=base["decision"], source="the_odds_api_current",
            model_id="football-1n2-shadow", data_cutoff=data_cutoff,
        )
        base["contender_records"] = _record_football_contenders(
            prediction=prediction, event_id=event_id, sport_key=sport_key, commence_time=first["commence_time"],
            observed_at=_iso(winamax["last_update"]), data_cutoff=data_cutoff, api_home=api_home, api_away=api_away,
            winamax=winamax, consensus=consensus,
        )
        shadow_record = base.get("shadow_record") or {}
        if shadow_record.get("created"):
            funnel["shadow_created"] += 1
        elif shadow_record.get("created") is False and not shadow_record.get("disabled") and not shadow_record.get("skipped"):
            funnel["shadow_reused"] += 1
        if not response.from_cache:
            base["prediction_id"] = _record_prediction_payload(prediction, provider_event_id=event_id)
        events.append(base)
    return {
        "provider": "The Odds API",
        "sport_key": sport_key,
        "league": league,
        "bookmakers_requested": list(ODDS_BOOKMAKERS),
        "quota": {
            "remaining": response.quota.remaining,
            "used": response.quota.used,
            "last_cost": response.quota.last_cost,
        },
        "from_cache": response.from_cache,
        "fetched_at": response.fetched_at,
        "storage": storage,
        "summary": {
            "events": len(events),
            **funnel,
            "winamax_available": sum(bool(x["winamax_available"]) for x in events),
            "events_truncated_flag": provider_event_count > len(events),
        },
        "events": events,
        "warning": "Verify every price directly with Winamax before any decision. No bet is placed automatically.",
    }


def _resolve_player(value: str, players: set[str]) -> str | None:
    by_normalized = {normalize_identity(player): player for player in players}
    return by_normalized.get(normalize_identity(value))


def _tennis_odds_slate(sport_key: str, surface: str, *, force_refresh: bool = False) -> dict[str, Any]:
    r = resources()
    history = r["tennis"]
    players = set(history["winner_name"]) | set(history["loser_name"])
    try:
        response = odds_client().current_odds(
            sport_key,
            markets=("h2h",),
            bookmakers=ODDS_BOOKMAKERS,
            force_refresh=force_refresh,
        )
    except OddsApiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OddsApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    rows = normalize_odds_payload(response.payload)
    storage = _persist_odds_response(rows, response, sport_key=sport_key, job_name="tennis_live_slate")
    markets = bookmaker_h2h_markets(rows)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for market in markets:
        grouped.setdefault(str(market["event_id"]), []).append(market)

    mode = r["metrics"].get("tennis", {}).get("serving_mode", "calibrated_model")
    calibrated = mode != "elo_only_uncalibrated"
    provider_event_count = len(grouped)
    grouped_items = list(grouped.items())[:SETTINGS.shadow_max_events]
    events: list[dict[str, Any]] = []
    for event_id, event_markets in grouped_items:
        first = event_markets[0]
        api_p1 = str(first["home_team"])
        api_p2 = str(first["away_team"])
        player_1 = _resolve_player(api_p1, players)
        player_2 = _resolve_player(api_p2, players)
        winamax = next((m for m in event_markets if m["bookmaker_key"] == "winamax_fr"), None)
        consensus = consensus_h2h(event_markets, exclude=("winamax_fr",))
        commence_ts = pd.to_datetime(first["commence_time"], utc=True, errors="coerce")
        in_play = bool(not pd.isna(commence_ts) and commence_ts <= pd.Timestamp.now(tz="UTC"))
        base = {
            "event_id": event_id,
            "sport_key": sport_key,
            "commence_time": _iso(first["commence_time"]),
            "api_player_1": api_p1,
            "api_player_2": api_p2,
            "model_player_1": player_1,
            "model_player_2": player_2,
            "surface": surface,
            "model_mode": mode,
            "winamax_available": winamax is not None,
            "in_play": in_play,
            "consensus": consensus,
            "decision": "abstention",
            "reasons": [],
        }
        if in_play:
            base["reasons"].append("match commencé : modèle pré-match désactivé")
            events.append(base)
            continue
        if player_1 is None or player_2 is None:
            base["reasons"].append("joueur non couvert par le modèle embarqué")
            events.append(base)
            continue
        prediction_date = pd.to_datetime(first["commence_time"], utc=True).date().isoformat()
        prediction = _tennis_prediction(TennisRequest(
            player_1=player_1,
            player_2=player_2,
            surface=surface,
            date=prediction_date,
        ))
        base["model"] = prediction
        if winamax is None:
            base["reasons"].append("cotes Winamax absentes du snapshot fournisseur")
            base["shadow_record"] = _record_shadow_payload(
                prediction, provider_event_id=event_id, sport_key=sport_key, commence_time=first["commence_time"],
                odds_observed_at=None, decision="abstention", source="the_odds_api_current",
                model_id="tennis-elo-experimental", data_cutoff=pd.to_datetime(history["date"], utc=True).max(),
            )
            events.append(base)
            continue
        labels = [api_p1, api_p2]
        if any(label not in winamax["odds"] for label in labels):
            base["reasons"].append("marché Winamax incomplet")
            base["shadow_record"] = _record_shadow_payload(
                prediction, provider_event_id=event_id, sport_key=sport_key, commence_time=first["commence_time"],
                odds_observed_at=_iso(winamax["last_update"]), decision="abstention", source="the_odds_api_current",
                model_id="tennis-elo-experimental", data_cutoff=pd.to_datetime(history["date"], utc=True).max(),
            )
            events.append(base)
            continue
        analysis = analyze_market(
            labels=[player_1, player_2],
            model_probabilities=[prediction["probabilities"]["player_1"], prediction["probabilities"]["player_2"]],
            decimal_odds=[winamax["odds"][api_p1], winamax["odds"][api_p2]],
            bookmaker="Winamax via The Odds API",
            market_type="vainqueur",
            observed_at=_iso(winamax["last_update"]),
            calibrated=calibrated,
        ).to_dict()
        base["winamax"] = {
            "odds": winamax["odds"],
            "probabilities": winamax["probabilities"],
            "overround": winamax["overround"],
            "last_update": _iso(winamax["last_update"]),
        }
        base["market_analysis"] = analysis
        prediction["market_analysis"] = analysis
        base["decision"] = "candidat recherche" if analysis["shortlist"] else "abstention"
        if not analysis["shortlist"]:
            reasons = sorted({reason for selection in analysis["selections"] for reason in selection["reasons"]})
            base["reasons"].extend(reasons or ["aucun edge robuste"])
        base["shadow_record"] = _record_shadow_payload(
            prediction, provider_event_id=event_id, sport_key=sport_key, commence_time=first["commence_time"],
            odds_observed_at=_iso(winamax["last_update"]), decision=base["decision"], source="the_odds_api_current",
            model_id="tennis-elo-experimental", data_cutoff=pd.to_datetime(history["date"], utc=True).max(),
        )
        if not response.from_cache:
            base["prediction_id"] = _record_prediction_payload(prediction, provider_event_id=event_id)
        events.append(base)
    return {
        "provider": "The Odds API",
        "sport_key": sport_key,
        "surface": surface,
        "bookmakers_requested": list(ODDS_BOOKMAKERS),
        "quota": {"remaining": response.quota.remaining, "used": response.quota.used, "last_cost": response.quota.last_cost},
        "from_cache": response.from_cache,
        "fetched_at": response.fetched_at,
        "storage": storage,
        "summary": {
            "events": len(events),
            "provider_events": provider_event_count,
            "events_truncated": provider_event_count > len(events),
            "winamax_available": sum(bool(x["winamax_available"]) for x in events),
            "research_candidates": sum(x["decision"] == "candidat recherche" for x in events),
            "shadow_created": sum(bool((x.get("shadow_record") or {}).get("created")) for x in events),
            "shadow_reused": sum((x.get("shadow_record") or {}).get("created") is False and not (x.get("shadow_record") or {}).get("disabled") and not (x.get("shadow_record") or {}).get("skipped") for x in events),
        },
        "events": events,
        "warning": "The bundled tennis model is uncalibrated and should normally abstain. Verify prices directly with Winamax.",
    }


def _future_prediction_date(raw_date: str | None, history_max: Any) -> str:
    cutoff = pd.to_datetime(history_max, utc=True, errors="raise")
    if raw_date is None:
        today = pd.Timestamp.now(tz="UTC").normalize()
        requested = today if today > cutoff else cutoff + pd.Timedelta(days=7)
        return requested.date().isoformat()
    try:
        requested = pd.to_datetime(raw_date, utc=True, errors="raise")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid ISO prediction date") from exc
    if requested <= cutoff:
        raise HTTPException(
            status_code=422,
            detail=f"Prediction date must be after the model data cutoff {cutoff.date().isoformat()}",
        )
    return requested.date().isoformat()


def _football_prediction(req: FootballRequest) -> dict[str, Any]:
    r = resources()
    history = r["football"]
    league_history = history[history["league"].astype(str) == req.league]
    if league_history.empty:
        raise HTTPException(status_code=422, detail=f"Unknown league in bundled model: {req.league}")
    teams = set(league_history["home_team"]) | set(league_history["away_team"])
    unknown = [x for x in (req.home_team, req.away_team) if x not in teams]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown team(s) for league {req.league}: {unknown}")
    date = _future_prediction_date(req.date, history["date"].max())
    fixture = pd.DataFrame([{
        "date": date,
        "league": req.league,
        "home_team": req.home_team,
        "away_team": req.away_team,
    }])
    try:
        pred = r["football_model"].predict_matches(history, fixture)[0]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    freshness = _model_freshness(data_cutoff=history["date"].max(), as_of=date)
    warning = "Research probability from a small real-data snapshot; not a production or betting guarantee."
    if freshness["stale"]:
        warning = (
            f"Research-only stale model: training data is {freshness['age_days']} days older than this fixture. "
            "Any market candidate is vetoed until the model is retrained."
        )
    payload: dict[str, Any] = {
        "sport": "football",
        "model_version": r["football_model_version"],
        "fixture": {"home_team": req.home_team, "away_team": req.away_team, "date": date, "league": req.league},
        "probabilities": {"home": pred["home_win"], "draw": pred["draw"], "away": pred["away_win"]},
        "expected_goals": {"home": pred["expected_home_goals"], "away": pred["expected_away_goals"]},
        "top_scores": pred["top_scores"],
        "model_freshness": freshness,
        "warning": warning,
    }
    if req.winamax_home_odds is not None:
        try:
            payload["market_analysis"] = analyze_three_way(
                home_label=req.home_team,
                draw_label="Match nul",
                away_label=req.away_team,
                home_probability=float(pred["home_win"]),
                draw_probability=float(pred["draw"]),
                away_probability=float(pred["away_win"]),
                home_odds=req.winamax_home_odds,
                draw_odds=req.winamax_draw_odds,
                away_odds=req.winamax_away_odds,
                observed_at=req.odds_observed_at,
                calibrated=True,
            )
            if freshness["stale"]:
                payload["market_analysis"] = _apply_market_veto(
                    payload["market_analysis"], reason="modèle trop ancien pour une sélection opérationnelle"
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


def _tennis_prediction(req: TennisRequest) -> dict[str, Any]:
    r = resources()
    players = set(r["tennis"]["winner_name"]) | set(r["tennis"]["loser_name"])
    unknown = [x for x in (req.player_1, req.player_2) if x not in players]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown player(s) in bundled model: {unknown}")
    history = r["tennis"]
    date = _future_prediction_date(req.date, history["date"].max())
    fixture = pd.DataFrame([{
        "date": date,
        "tour": "ATP",
        "surface": req.surface,
        "tournament_level": req.tournament_level,
        "best_of": req.best_of,
        "player_1": req.player_1,
        "player_2": req.player_2,
    }])
    try:
        p1 = float(r["tennis_model"].predict_matches(history, fixture)[0])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    mode = r["metrics"].get("tennis", {}).get("serving_mode", "calibrated_model")
    payload: dict[str, Any] = {
        "sport": "tennis",
        "fixture": {
            "player_1": req.player_1,
            "player_2": req.player_2,
            "surface": req.surface,
            "date": date,
            "tournament_level": req.tournament_level,
            "best_of": req.best_of,
        },
        "probabilities": {"player_1": p1, "player_2": 1.0 - p1},
        "symmetry_check": p1 + (1.0 - p1),
        "model_mode": mode,
        "warning": (
            "Uncalibrated Elo research probability: the bundled tennis snapshot has too few "
            "tournament timestamps for a valid calibration. Not a production or betting guarantee."
            if mode == "elo_only_uncalibrated"
            else "Research probability from a small real-data snapshot; not a production or betting guarantee."
        ),
    }
    if req.winamax_player_1_odds is not None:
        try:
            payload["market_analysis"] = analyze_two_way(
                player_1=req.player_1,
                player_2=req.player_2,
                player_1_probability=p1,
                player_1_odds=req.winamax_player_1_odds,
                player_2_odds=req.winamax_player_2_odds,
                observed_at=req.odds_observed_at,
                calibrated=mode != "elo_only_uncalibrated",
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if not SETTINGS.auth_required or request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse((STATIC / "login.html").read_text(encoding="utf-8"))


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request) -> dict[str, Any]:
    if not SETTINGS.auth_required:
        return {"authenticated": True, "auth_required": False, "csrf_token": None}
    issues = SETTINGS.readiness_issues()
    if any(issue.startswith("APP_PASSWORD") or issue.startswith("APP_SESSION_SECRET") for issue in issues):
        raise HTTPException(status_code=503, detail="Cloud authentication is not configured")
    key = client_key(request)
    decision = LOGIN_LIMITER.check(key)
    if not decision.allowed:
        return JSONResponse(
            {"detail": "Too many login attempts", "retry_after_seconds": decision.retry_after_seconds},
            status_code=429,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    if not verify_password(req.password, SETTINGS):
        LOGIN_LIMITER.fail(key)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    LOGIN_LIMITER.success(key)
    csrf = establish_session(request)
    return {"authenticated": True, "auth_required": True, "csrf_token": csrf}


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    return {
        "authenticated": bool(request.session.get("authenticated")) or not SETTINGS.auth_required,
        "auth_required": SETTINGS.auth_required,
        "csrf_token": request.session.get("csrf") if SETTINGS.auth_required else None,
        "environment": SETTINGS.environment,
    }


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    clear_session(request)
    return {"authenticated": False}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "service": "sports-prediction-lab",
        "automatic_bet_placement": False,
        "the_odds_api_configured": odds_client().config.configured,
        "shadow_mode_enabled": SETTINGS.shadow_enabled,
    }


@app.get("/api/release")
def release_proof() -> dict[str, Any]:
    evidence = build_release_evidence(ROOT, version=app.version)
    app_info = evidence.get("app") or {}
    football = evidence.get("football_model") or {}
    integrity = evidence.get("integrity") or {}
    return {
        "status": "ok" if integrity.get("artifact_integrity_ok") else "degraded",
        "release_id": evidence.get("release_id"),
        "version": app.version,
        "source_commit": app_info.get("source_commit"),
        "deployment_id": app_info.get("deployment_id"),
        "football_model_version": football.get("model_version"),
        "football_model_sha256": football.get("artifact_sha256"),
        "dataset_sha256": football.get("dataset_sha256"),
        "artifact_integrity_ok": integrity.get("artifact_integrity_ok"),
        "automatic_model_promotion": False,
        "profitability_claim": False,
        "automatic_bet_placement": False,
    }


@app.get("/api/ready")
def ready():
    issues = list(SETTINGS.readiness_issues())
    try:
        r = resources()
        models = {
            "football": r["football_model"].artifacts is not None,
            "tennis": r["tennis_model"].artifacts is not None,
            "artifact_integrity_verified": True,
        }
    except Exception:
        models = {"football": False, "tennis": False, "artifact_integrity_verified": False}
        issues.append("model artifacts unavailable")
    db = database_summary()
    if not db["connected"]:
        issues.append("database unavailable")

    # Startup failures are diagnostics, not permanent readiness latches.
    # A dependency may recover after process startup (or a test may have
    # deliberately exercised a failure path). Current live checks are the
    # source of truth for readiness. Clear stale startup errors once the
    # corresponding dependency is demonstrably healthy.
    if db["connected"]:
        STARTUP_STATE["database_error"] = None
    elif STARTUP_STATE.get("database_error"):
        issues.append(f"database startup error: {STARTUP_STATE['database_error']}")

    if models.get("football") and models.get("tennis") and models.get("artifact_integrity_verified"):
        STARTUP_STATE["model_error"] = None
    elif STARTUP_STATE.get("model_error"):
        issues.append(f"model startup error: {STARTUP_STATE['model_error']}")

    payload = {
        "status": "ready" if not issues else "not_ready",
        "version": app.version,
        "issues": sorted(set(issues)),
        "models": models,
        "database": db,
        "the_odds_api_configured": odds_client().config.configured,
        "auth_required": SETTINGS.auth_required,
        "shadow_mode": {"enabled": SETTINGS.shadow_enabled, "latest_cycle": latest_shadow_cycle()},
    }
    return JSONResponse(payload, status_code=200 if not issues else 503)


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    r = resources()
    f = r["football"]
    t = r["tennis"]
    return {
        "football_teams": sorted(set(f["home_team"]) | set(f["away_team"])),
        "tennis_players": sorted(set(t["winner_name"]) | set(t["loser_name"])),
        "surfaces": ["hard", "clay", "grass", "carpet"],
        "data": {
            "football_rows": len(f),
            "tennis_rows": len(t),
            "football_cutoff": pd.to_datetime(f["date"], utc=True).max().date().isoformat(),
            "tennis_cutoff": pd.to_datetime(t["date"], utc=True).max().date().isoformat(),
        },
    }


@app.get("/api/metrics")
def metrics() -> dict[str, Any]:
    r = resources()
    return {
        "metrics": r["metrics"],
        "backtest": r["backtest"],
        "provenance": r["provenance"],
        "artifact_manifest": r["artifact_manifest"],
        "market_benchmark": benchmark_summary((latest_benchmark_run("soccer_epl") or {}).get("report")),
    }


def _system_status_payload() -> dict[str, Any]:
    evidence = build_release_evidence(ROOT, version=app.version)
    db = database_summary()
    models = list_models()
    current_resource = resources()
    football_model_version = current_resource["football_model_version"]
    football_registered = next(
        (
            model for model in models
            if model.get("sport") == "football" and model.get("version") == football_model_version
        ),
        None,
    )
    integrity = evidence.get("integrity") or {}
    issues: list[str] = []
    if not integrity.get("artifact_integrity_ok"):
        issues.append("artifact integrity mismatch")
    if not db.get("connected"):
        issues.append("database unavailable")
    if football_registered is None:
        issues.append("running football model is not registered")
    if (evidence.get("app") or {}).get("source_commit") == "unknown":
        issues.append("running source commit is unknown")
    latest_cycle = latest_shadow_cycle()
    latest_release = (list_releases(limit=1) or [None])[0]
    return {
        "status": "verified" if not issues else "degraded",
        "issues": issues,
        "release": evidence,
        "registered_release": latest_release,
        "deployment_contract": {
            "api_version_matches_manifest": (evidence.get("app") or {}).get("version") == app.version,
            "running_commit_known": (evidence.get("app") or {}).get("source_commit") != "unknown",
            "artifact_integrity_verified": bool(integrity.get("artifact_integrity_ok")),
            "running_model_registered": football_registered is not None,
        },
        "models": models,
        "model_status_history": model_status_history(limit=20),
        "database": db,
        "shadow": {
            "latest_cycle": latest_cycle,
            "summary": shadow_summary(sport_key="soccer_epl"),
        },
        "benchmark": benchmark_summary((latest_benchmark_run("soccer_epl") or {}).get("report")),
        "model_decision": _model_decision_payload("soccer_epl"),
        "continuity": {
            "operation": "GitHub Actions → Generate handoff package → Run workflow",
            "workflow": "generate-handoff.yml",
            "artifact": "sports-prediction-handoff-v4.0",
            "local_python_required": False,
            "files": [
                "START_HERE_NEXT_CHAT.md",
                "handoff/HANDOFF_CURRENT.md",
                "handoff/HANDOFF_CURRENT.json",
            ],
            "secrets_exported": False,
        },
    }


def _model_decision_payload(sport_key: str = "soccer_epl") -> dict[str, Any]:
    persisted = latest_model_decision(sport_key)
    run = latest_benchmark_run(sport_key)
    report = (run or {}).get("report")
    summary = shadow_summary(sport_key=sport_key)
    models = list_models()
    champion_model = next((m for m in models if m.get("sport") == "football" and m.get("status") == "active"), None)
    if champion_model is None:
        champion_model = next((m for m in models if m.get("model_id") == "football-1n2-shadow"), None)
    champion_key = None
    if champion_model:
        champion_key = f"{champion_model.get('model_id')}@{champion_model.get('version')}"
    computed = build_model_decision(
        report, shadow_summary=summary, champion="model", champion_model_key=champion_key,
    )
    return {
        "source": "computed_from_latest_evidence",
        "sport_key": sport_key,
        "benchmark_run_id": (run or {}).get("id"),
        "persisted": persisted,
        "decision": computed,
    }


@app.get("/api/model-decision")
def model_decision(sport_key: str = "soccer_epl") -> dict[str, Any]:
    return _model_decision_payload(sport_key)


@app.get("/api/system/status")
def system_status() -> dict[str, Any]:
    return _system_status_payload()


@app.get("/api/control-center")
def control_center() -> dict[str, Any]:
    status = _system_status_payload()
    return build_control_center(
        release=status.get("release") or {},
        database=status.get("database") or {},
        models=status.get("models") or [],
        shadow_cycle=((status.get("shadow") or {}).get("latest_cycle")),
        benchmark=status.get("benchmark") or {},
        model_decision=status.get("model_decision") or {},
        backfills=recent_backfill_jobs(limit=10),
    )


@app.get("/api/system/releases")
def system_releases(limit: int = 20) -> dict[str, Any]:
    return {"releases": list_releases(limit=limit)}


@app.get("/api/system/handoff")
def system_handoff() -> dict[str, Any]:
    status = _system_status_payload()
    release = status.get("release") or {}
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "verified": status.get("status") == "verified",
        "app": release.get("app"),
        "football_model": release.get("football_model"),
        "deployment_contract": status.get("deployment_contract"),
        "database": status.get("database"),
        "shadow": status.get("shadow"),
        "benchmark": status.get("benchmark"),
        "model_decision": status.get("model_decision"),
        "issues": status.get("issues"),
        "secrets_exported": False,
    }


@app.post("/api/admin/models/status")
def update_model_status(request: ModelStatusRequest) -> dict[str, Any]:
    try:
        transition = set_model_status(
            model_id=request.model_id,
            version=request.version,
            new_status=request.new_status,
            reason=request.reason,
            actor=request.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok", "transition": transition, "models": list_models()}


@app.get("/api/history/predictions")
def prediction_history(limit: int = 50) -> dict[str, Any]:
    return {"predictions": recent_predictions(limit), "database": database_summary()}


@app.get("/api/history/sync-runs")
def sync_history(limit: int = 20) -> dict[str, Any]:
    return {"runs": recent_sync_runs(limit), "database": database_summary()}


@app.get("/api/bets/today")
def bets_today(date: str | None = None) -> dict[str, Any]:
    requested = date or datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    if not DATE_RE.fullmatch(requested):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    persisted = [row for row in predictions_for_date(requested) if row.get("market_analysis")]
    if persisted:
        now = pd.Timestamp.now(tz="UTC")
        events: list[dict[str, Any]] = []
        for row in persisted:
            fixture = row.get("fixture") or {}
            analysis = row.get("market_analysis") or {}
            sport = str(row.get("sport"))
            event_name = (
                f"{fixture.get('home_team', '—')} — {fixture.get('away_team', '—')}"
                if sport == "football"
                else f"{fixture.get('player_1', '—')} — {fixture.get('player_2', '—')}"
            )
            observed = pd.to_datetime(analysis.get("observed_at"), utc=True, errors="coerce")
            age_minutes = None if pd.isna(observed) else max(0.0, (now - observed).total_seconds() / 60.0)
            decision = str(row.get("decision") or "abstention")
            reasons = sorted({
                str(reason)
                for selection in analysis.get("selections", [])
                for reason in selection.get("reasons", [])
            })
            if age_minutes is None or age_minutes > SETTINGS.odds_stale_minutes:
                decision = "à actualiser"
                reasons.append("cote absente ou trop ancienne au moment de l’affichage")
            if not reasons and decision != "candidat recherche":
                reasons.append(str(analysis.get("warning") or "aucun edge robuste validé"))
            events.append({
                "sport": sport,
                "event": event_name,
                "competition": fixture.get("league") or fixture.get("tournament_level") or "marché pré-match",
                "market": analysis.get("market_type", "vainqueur"),
                "decision": decision,
                "reasons": reasons,
                "winamax_odds": bool(analysis),
                "observed_at": _iso(observed),
                "odds_age_minutes": age_minutes,
                "prediction_id": row.get("id"),
            })
        candidates = sum(event["decision"] == "candidat recherche" for event in events)
        return {
            "date": requested,
            "bookmaker": "Winamax via The Odds API",
            "source": "postgresql",
            "summary": {
                "events_reviewed": len(events),
                "research_candidates": candidates,
                "abstentions": len(events) - candidates,
            },
            "events": events,
            "warning": "Prices are reclassified as stale at display time. Verify every price directly with Winamax.",
        }
    path = DAILY_SLATE / f"{requested}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["source"] = "bundled_snapshot"
        return payload
    return {
        "date": requested,
        "bookmaker": "Winamax",
        "source": "empty",
        "summary": {"events_reviewed": 0, "research_candidates": 0, "abstentions": 0},
        "events": [],
        "warning": "No fresh persisted slate is available. Run the sync job or load the odds feed.",
    }




@app.get("/api/shadow/summary")
def shadow_mode_summary(sport_key: str = "soccer_epl") -> dict[str, Any]:
    if not SPORT_KEY_RE.fullmatch(sport_key):
        raise HTTPException(status_code=422, detail="Invalid sport_key")
    return {
        "enabled": SETTINGS.shadow_enabled,
        "summary": shadow_summary(sport_key=sport_key),
        "latest_cycle": latest_shadow_cycle(),
        "models": list_models(),
        "database": database_summary(),
        "automatic_bet_placement": False,
        "fresh_rebuild": resources().get("fresh_rebuild"),
        "football_data_source": resources().get("football_data_source"),
    }


@app.get("/api/shadow/predictions")
def shadow_prediction_history(limit: int = 50, sport_key: str | None = None, status: str | None = None) -> dict[str, Any]:
    if sport_key and not SPORT_KEY_RE.fullmatch(sport_key):
        raise HTTPException(status_code=422, detail="Invalid sport_key")
    if status and status not in {"open", "settled", "invalid", "experimental_unsettled"}:
        raise HTTPException(status_code=422, detail="Invalid shadow status")
    return {"predictions": recent_shadow_predictions(limit, sport_key=sport_key, status=status)}


@app.get("/api/models")
def model_registry() -> dict[str, Any]:
    return {"models": list_models()}


@app.get("/api/benchmark/summary")
def market_benchmark_summary(sport_key: str = "soccer_epl") -> dict[str, Any]:
    if not SPORT_KEY_RE.fullmatch(sport_key):
        raise HTTPException(status_code=422, detail="Invalid sport_key")
    run = latest_benchmark_run(sport_key)
    if run is None:
        artifact = ROOT / "artifacts/market_benchmark_v3_4.json"
        if artifact.exists():
            report = json.loads(artifact.read_text(encoding="utf-8"))
            return {"source": "artifact", "summary": benchmark_summary(report), "report": report}
        return {
            "source": "none",
            "summary": benchmark_summary(None),
            "report": None,
            "required_next_step": "Run the historical backfill and benchmark worker with a reviewed credit cap.",
        }
    return {"source": "postgresql", "summary": run.get("summary") or benchmark_summary(run.get("report")), "report": run.get("report"), "run": {k: v for k, v in run.items() if k != "report"}}


@app.get("/api/evidence")
def evidence_report() -> dict[str, Any]:
    candidates = [
        ROOT / "artifacts" / "evidence_report_v3_9.json",
        ROOT / "artifacts" / "evidence_report_v3_8.json",
    ]
    artifact = next((path for path in candidates if path.exists()), None)
    if artifact is None:
        return {
            "source": "none",
            "report": {
                "schema_version": "2.0",
                "app_version": APP_VERSION,
                "quality_gate": {"status": "not_run", "accepted": False, "reason": "no historical evidence report has been published"},
                "gates": {},
                "funnel": {},
                "counts": {},
                "rates": {},
                "bookmaker_coverage": [],
                "blockers": [],
                "warnings": [],
                "responsible_use": {"profitability_claim": False, "stake_recommendation": False, "automatic_bet_placement": False},
            },
            "required_next_step": "GitHub Actions → Recompute latest evidence → Run workflow (zero provider credits).",
        }
    try:
        report = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"Evidence report unreadable: {type(exc).__name__}") from exc
    if artifact.name == "evidence_report_v3_8.json" or str(report.get("schema_version") or "1.0") != "2.0":
        return {
            "source": "legacy_v3_8_requires_recompute",
            "report": {
                "schema_version": "2.0",
                "app_version": APP_VERSION,
                "quality_gate": {
                    "status": "needs_recompute",
                    "accepted": False,
                    "reason": "legacy V3.8 denominators are not displayed because discovered events were mixed with executed targets",
                },
                "gates": {},
                "funnel": {},
                "counts": {},
                "rates": {},
                "bookmaker_coverage": [],
                "consumed_credits": report.get("consumed_credits", 0),
                "plan_request_id": report.get("plan_request_id"),
                "blockers": ["legacy_denominators_require_zero_credit_recompute"],
                "warnings": [],
                "next_action": "GitHub Actions → Recompute latest evidence → Run workflow. This uses the saved artifact and consumes zero provider credits.",
                "responsible_use": {"profitability_claim": False, "stake_recommendation": False, "automatic_bet_placement": False},
            },
        }
    return {"source": artifact.name, "report": report}


@app.get("/api/coverage-preflight")
def coverage_preflight() -> dict[str, Any]:
    artifact = ROOT / "artifacts" / "coverage_preflight_v4_2.json"
    if not artifact.exists():
        return {
            "source": "none",
            "report": {
                "schema_version": "1.0",
                "app_version": APP_VERSION,
                "decision": "NOT_RUN",
                "reason": "coverage_preflight_missing",
                "accepted": False,
                "baseline_coverage": 0.0,
                "recommended_selected_events": None,
                "preflight_credits": 0,
                "maximum_preflight_credits": 0,
                "candidate_campaign_plan": None,
            },
            "required_next_step": "GitHub Actions → Estimate evidence coverage.",
        }
    try:
        report = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"Coverage preflight unreadable: {type(exc).__name__}") from exc
    return {"source": artifact.name, "report": report}


@app.get("/api/evidence-campaign")
def evidence_campaign() -> dict[str, Any]:
    artifact = ROOT / "artifacts" / "evidence_campaign_v4.json"
    if not artifact.exists():
        return {
            "source": "none",
            "report": {
                "schema_version": "1.0",
                "app_version": APP_VERSION,
                "decision": "not_run",
                "completed_stage": None,
                "next_stage": 30,
                "scale_gate": {"accepted": False, "reason": "no_campaign_report"},
                "budget": {},
                "automatic_model_promotion": False,
                "profitability_claim": False,
                "automatic_bet_placement": False,
            },
            "required_next_step": "GitHub Actions → Run evidence campaign → dry_run.",
        }
    try:
        report = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"Campaign report unreadable: {type(exc).__name__}") from exc
    return {"source": artifact.name, "report": report}


@app.get("/api/admin/data-quality")
def data_quality(limit: int = 100) -> dict[str, Any]:
    return {"issues": recent_data_quality_issues(limit), "database": database_summary()}


@app.get("/api/admin/backfills")
def backfill_history(limit: int = 20) -> dict[str, Any]:
    return {"jobs": recent_backfill_jobs(limit), "database": database_summary()}


@app.get("/api/odds/status")
def odds_status() -> dict[str, Any]:
    client = odds_client()
    db = database_summary()
    return {
        "provider": "The Odds API",
        "configured": client.config.configured,
        "key_exposed_to_frontend": False,
        "cache_backend": "provider cache + PostgreSQL snapshots",
        "quota": client.quota_status(),
        "supported_bookmakers": list(ODDS_BOOKMAKERS),
        "winamax_key": "winamax_fr",
        "automatic_bet_placement": False,
        "database": db,
        "stale_after_minutes": SETTINGS.odds_stale_minutes,
    }


@app.post("/api/odds/historical/estimate")
def historical_estimate(req: HistoricalEstimateRequest) -> dict[str, Any]:
    cost = OddsApiClient.estimate_quota_cost(
        markets=req.markets,
        bookmakers=req.bookmakers,
        historical=req.historical,
        snapshot_count=req.snapshot_count,
    )
    return {
        "snapshot_count": req.snapshot_count,
        "markets": req.markets,
        "bookmakers": req.bookmakers,
        "historical": req.historical,
        "estimated_credits": cost,
        "dry_run_required": True,
    }


@app.get("/api/odds/sports")
def odds_sports(group: str | None = None) -> dict[str, Any]:
    try:
        response = odds_client().list_sports()
    except OddsApiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OddsApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    sports = response.payload if isinstance(response.payload, list) else []
    if group:
        sports = [item for item in sports if str(item.get("group", "")).casefold() == group.casefold()]
    safe = [{"key": x.get("key"), "group": x.get("group"), "title": x.get("title"), "active": bool(x.get("active"))} for x in sports]
    return {"sports": safe, "quota": {"remaining": response.quota.remaining, "used": response.quota.used, "last_cost": response.quota.last_cost}, "from_cache": response.from_cache}


@app.get("/api/odds/tennis/slate")
def odds_tennis_slate(sport_key: str, surface: str = "hard") -> dict[str, Any]:
    if not SPORT_KEY_RE.fullmatch(sport_key) or not sport_key.startswith("tennis_"):
        raise HTTPException(status_code=422, detail="Invalid tennis sport_key")
    surface = surface.lower()
    if surface not in {"hard", "clay", "grass", "carpet"}:
        raise HTTPException(status_code=422, detail="Unsupported surface")
    return _tennis_odds_slate(sport_key, surface, force_refresh=False)


@app.get("/api/odds/football/slate")
def odds_football_slate(
    sport_key: str = "soccer_epl",
    league: str | None = None,
) -> dict[str, Any]:
    if not SPORT_KEY_RE.fullmatch(sport_key):
        raise HTTPException(status_code=422, detail="Invalid sport_key")
    resolved_league = league or SPORT_LEAGUE_MAP.get(sport_key)
    if not resolved_league:
        raise HTTPException(status_code=422, detail="No bundled model mapping for this sport_key")
    return _football_odds_slate(sport_key, resolved_league, force_refresh=False)


@app.post("/api/football/predict")
def predict_football(req: FootballRequest) -> dict[str, Any]:
    payload = _football_prediction(req)
    payload["prediction_id"] = _record_prediction_payload(payload)
    return payload


@app.post("/api/tennis/predict")
def predict_tennis(req: TennisRequest) -> dict[str, Any]:
    payload = _tennis_prediction(req)
    payload["prediction_id"] = _record_prediction_payload(payload)
    return payload
