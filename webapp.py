from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping
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
    due_shadow_events,
    init_database,
    persist_odds_rows,
    persist_event_result,
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
    record_prediction_once,
    record_sync_run,
    record_model_decision,
    record_shadow_prediction,
    record_benchmark_run,
    record_data_quality_issue,
    research_credits_consumed_on,
    register_dataset_catalog,
    register_holdout_generation,
    settle_shadow_predictions,
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
    OddsApiNetworkDisabled,
)
from sports_predictor.identity import football_model_name, normalize_identity
from sports_predictor.odds_data import bookmaker_h2h_markets, consensus_h2h, normalize_odds_payload, normalize_scores_payload
from sports_predictor.market_benchmark import benchmark_summary
from sports_predictor.champion_challenger import build_model_decision
from sports_predictor.control_center import build_control_center
from sports_predictor.shadow_mode import shadow_horizon
from sports_predictor.roi_lab import (
    SignalPolicy,
    build_champion_challenger_report,
    build_roi_lab_report,
    score_roi_meta_model,
)
from sports_predictor.feature_lab import build_feature_lab_report
from sports_predictor.challenger_factory import build_challenger_factory_report
from sports_predictor.evidence_acceleration import build_evidence_acceleration_report
from sports_predictor.controlled_decision import build_controlled_model_decision_report
from sports_predictor.daily_product import (
    DailyFixtureError,
    DailyFixtureSource,
    build_model_diagnostics,
    fixture_identifier,
    probability_diagnostics,
    select_fixture_window,
)

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
    title="Sports Prediction Lab V4.6 Robust Calibration & Feature Lab",
    version=APP_VERSION,
    description="Dual-sport daily research product with compact interface, bounded calibration experiments, shadow signals and simulated bankroll evaluation.",
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


class DailyResearchRefreshRequest(BaseModel):
    date: str | None = None
    max_credits: int = Field(default=3, ge=1, le=20)
    automation: bool = False
    tennis_limit: int = Field(default=2, ge=0, le=10)
    tennis_sport_keys: list[str] = Field(default_factory=list, max_length=10)
    confirmation: str = Field(min_length=1, max_length=64)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str | None):
        if value is not None and not DATE_RE.fullmatch(value):
            raise ValueError("date must use YYYY-MM-DD")
        return value

    @field_validator("tennis_sport_keys")
    @classmethod
    def valid_tennis_keys(cls, values: list[str]):
        cleaned = []
        for value in values:
            token = str(value).strip()
            if not SPORT_KEY_RE.fullmatch(token) or not token.startswith("tennis_"):
                raise ValueError("tennis_sport_keys must contain valid tennis_* tokens")
            cleaned.append(token)
        return cleaned


class DailyResearchSettleRequest(BaseModel):
    max_credits: int = Field(default=3, ge=1, le=20)
    automation: bool = False
    confirmation: str = Field(min_length=1, max_length=64)


class ResearchChampionPromotionRequest(BaseModel):
    candidate_id: str = Field(pattern=r"^RCH-[A-F0-9]{20}$")
    confirmation: str = Field(min_length=1, max_length=64)
    note: str = Field(default="manual review", min_length=3, max_length=500)


class FeatureLabRunRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=64)


class ChallengerFactoryRunRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=64)


class EvidenceAccelerationRunRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=64)
    source: str = Field(default="local_tennis_archive", min_length=1, max_length=200)
    license_status: str = Field(default="research_only", pattern=r"^(unknown|research_only|approved)$")


class ControlledModelDecisionRunRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=64)


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


@lru_cache(maxsize=1)
def fixture_source() -> DailyFixtureSource:
    return DailyFixtureSource(
        ROOT / "data" / "daily_fixtures",
        cache_ttl_seconds=SETTINGS.daily_fixture_cache_hours * 60 * 60,
    )


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
    decision = (
        "candidat recherche" if analysis and analysis.get("shortlist")
        else ("abstention" if analysis else "model_only")
    )
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
            allow_network=SETTINGS.daily_odds_enabled and SETTINGS.daily_odds_max_credits >= 1,
        )
    except OddsApiNetworkDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
            allow_network=SETTINGS.daily_odds_enabled and SETTINGS.daily_odds_max_credits >= 1,
        )
    except OddsApiNetworkDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


def _football_model_only_prediction(
    *,
    home_team: str,
    away_team: str,
    date: str | None,
    league: str,
    allow_cold_start: bool,
) -> dict[str, Any]:
    r = resources()
    history = r["football"]
    league_history = history[history["league"].astype(str) == league]
    if league_history.empty:
        raise HTTPException(status_code=422, detail=f"Unknown league in bundled model: {league}")
    teams = set(league_history["home_team"]) | set(league_history["away_team"])
    unknown = [x for x in (home_team, away_team) if x not in teams]
    if unknown and not allow_cold_start:
        raise HTTPException(status_code=422, detail=f"Unknown team(s) for league {league}: {unknown}")
    prediction_date = _future_prediction_date(date, history["date"].max())
    fixture = pd.DataFrame([{
        "date": prediction_date,
        "league": league,
        "home_team": home_team,
        "away_team": away_team,
    }])
    try:
        pred = r["football_model"].predict_matches(history, fixture)[0]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    freshness = _model_freshness(data_cutoff=history["date"].max(), as_of=prediction_date)
    warning = "Research probability from a small real-data snapshot; not a production or betting guarantee."
    coverage_mode = "historical_team_coverage"
    model_weight = 1.0
    if unknown:
        coverage_mode = "cold_start_league_priors"
        model_weight = 0.5 if len(unknown) == 1 else 0.25
        home_goals = pd.to_numeric(league_history["home_goals"], errors="coerce")
        away_goals = pd.to_numeric(league_history["away_goals"], errors="coerce")
        valid_results = home_goals.notna() & away_goals.notna()
        home_goals = home_goals[valid_results]
        away_goals = away_goals[valid_results]
        total_results = max(1, len(home_goals))
        prior = {
            "home": float((home_goals > away_goals).sum() / total_results),
            "draw": float((home_goals == away_goals).sum() / total_results),
            "away": float((home_goals < away_goals).sum() / total_results),
        }
        raw_probabilities = {
            "home": float(pred["home_win"]),
            "draw": float(pred["draw"]),
            "away": float(pred["away_win"]),
        }
        shrunk = {
            key: model_weight * raw_probabilities[key] + (1.0 - model_weight) * prior[key]
            for key in ("home", "draw", "away")
        }
        normalizer = sum(shrunk.values()) or 1.0
        pred["home_win"] = shrunk["home"] / normalizer
        pred["draw"] = shrunk["draw"] / normalizer
        pred["away_win"] = shrunk["away"] / normalizer
        league_home_mean = float(home_goals.mean()) if len(home_goals) else 1.45
        league_away_mean = float(away_goals.mean()) if len(away_goals) else 1.15
        pred["expected_home_goals"] = model_weight * float(pred["expected_home_goals"]) + (1.0 - model_weight) * league_home_mean
        pred["expected_away_goals"] = model_weight * float(pred["expected_away_goals"]) + (1.0 - model_weight) * league_away_mean
        warning = (
            "Cold-start research probability: one or more clubs have no Premier League history in the current "
            "training window, so the model is shrunk toward league priors. No market shortlist is permitted."
        )
    if freshness["stale"]:
        warning = (
            f"Research-only stale model: training data is {freshness['age_days']} days older than this fixture. "
            "Any market candidate is vetoed until the model is retrained."
        )
    payload: dict[str, Any] = {
        "sport": "football",
        "model_version": r["football_model_version"],
        "fixture": {
            "home_team": home_team,
            "away_team": away_team,
            "date": prediction_date,
            "league": league,
            "coverage_mode": coverage_mode,
            "cold_start_teams": unknown,
            "cold_start_model_weight": model_weight,
        },
        "probabilities": {"home": pred["home_win"], "draw": pred["draw"], "away": pred["away_win"]},
        "expected_goals": {"home": pred["expected_home_goals"], "away": pred["expected_away_goals"]},
        "top_scores": pred["top_scores"],
        "model_freshness": freshness,
        "market_eligible": not unknown and not freshness["stale"],
        "warning": warning,
    }
    return payload


def _football_prediction(req: FootballRequest) -> dict[str, Any]:
    payload = _football_model_only_prediction(
        home_team=req.home_team,
        away_team=req.away_team,
        date=req.date,
        league=req.league,
        allow_cold_start=False,
    )
    freshness = payload["model_freshness"]
    if req.winamax_home_odds is not None:
        try:
            payload["market_analysis"] = analyze_three_way(
                home_label=req.home_team,
                draw_label="Match nul",
                away_label=req.away_team,
                home_probability=float(payload["probabilities"]["home"]),
                draw_probability=float(payload["probabilities"]["draw"]),
                away_probability=float(payload["probabilities"]["away"]),
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



def _model_diagnostics_payload() -> dict[str, Any]:
    try:
        current = resources()
        history = current["football"]
        teams = set(history["home_team"].astype(str)) | set(history["away_team"].astype(str))
        preferred = [team for team in ("Arsenal", "Chelsea", "Liverpool", "Man City") if team in teams]
        if len(preferred) < 2:
            preferred = sorted(teams)[:2]
        probe: dict[str, Any] | None = None
        probe_error: str | None = None
        if len(preferred) >= 2:
            probe_date = (pd.to_datetime(history["date"], utc=True).max() + pd.Timedelta(days=7)).date().isoformat()
            try:
                probe = _football_prediction(FootballRequest(
                    home_team=preferred[0], away_team=preferred[1], date=probe_date, league="E0",
                ))
            except Exception as exc:  # diagnostic output keeps only the type
                probe_error = type(exc).__name__
        registry = next(
            (
                row for row in list_models()
                if row.get("model_id") == "football-1n2-shadow"
                and row.get("version") == current["football_model_version"]
            ),
            None,
        )
        freshness = _model_freshness(
            data_cutoff=history["date"].max(), as_of=datetime.now(ZoneInfo("UTC")),
        )
        diagnostics = build_model_diagnostics(
            model_loaded=current["football_model"].artifacts is not None,
            artifact_integrity_verified=True,
            model_version=current["football_model_version"],
            data_cutoff=history["date"].max(),
            metrics=current["metrics"].get("football") or {},
            model_freshness=freshness,
            probe_probabilities=(probe or {}).get("probabilities"),
            registry_status=(registry or {}).get("status"),
        )
        diagnostics["probe_fixture"] = (probe or {}).get("fixture")
        diagnostics["probe_error"] = probe_error
        diagnostics["credit_firewall"] = {
            "model_only_cost_credits": 0,
            "daily_odds_enabled": SETTINGS.daily_odds_enabled,
            "daily_odds_max_credits": SETTINGS.daily_odds_max_credits,
            "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
        }
        return diagnostics
    except Exception as exc:
        return {
            "schema_version": "1.0",
            "status": "blocked",
            "hard_failures": ["diagnostic_runtime_failure"],
            "error_type": type(exc).__name__,
            "product_readiness": {"model_only_predictions": False, "market_shortlist": False},
            "credit_firewall": {
                "model_only_cost_credits": 0,
                "daily_odds_enabled": SETTINGS.daily_odds_enabled,
                "daily_odds_max_credits": SETTINGS.daily_odds_max_credits,
                "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
            },
        }


def _daily_event_from_prediction(row: dict[str, Any]) -> dict[str, Any]:
    fixture = row.get("fixture") or {}
    probabilities = row.get("probabilities") or {}
    analysis = row.get("market_analysis") or None
    diagnostics = probability_diagnostics(probabilities)
    event_name = f"{fixture.get('home_team', '—')} — {fixture.get('away_team', '—')}"
    reasons: list[str] = []
    if not diagnostics["valid"]:
        reasons.append("probabilités invalides : " + ", ".join(diagnostics["issues"]))
    if analysis is None:
        reasons.append("cotes non demandées : prédiction modèle seule, coût API nul")
        decision = "probabilités seulement"
    else:
        observed = pd.to_datetime(analysis.get("observed_at"), utc=True, errors="coerce")
        age_minutes = None if pd.isna(observed) else max(0.0, (pd.Timestamp.now(tz="UTC") - observed).total_seconds() / 60.0)
        decision = str(row.get("decision") or "abstention")
        reasons.extend(sorted({
            str(reason)
            for selection in analysis.get("selections", [])
            for reason in selection.get("reasons", [])
        }))
        if age_minutes is None or age_minutes > SETTINGS.odds_stale_minutes:
            decision = "à actualiser"
            reasons.append("cote absente ou trop ancienne au moment de l’affichage")
    freshness = fixture.get("model_freshness") or {}
    coverage_mode = str(fixture.get("coverage_mode") or "historical_team_coverage")
    cold_start_teams = list(fixture.get("cold_start_teams") or [])
    cold_start_model_weight = float(fixture.get("cold_start_model_weight") or 1.0)
    if coverage_mode == "cold_start_league_priors":
        reasons.append(
            "confiance réduite : "
            + ", ".join(cold_start_teams or ["club sans historique récent"])
            + " utilise des priors de championnat"
        )
    if freshness.get("stale"):
        reasons.append("modèle trop ancien pour une sélection de marché")
    return {
        "sport": str(row.get("sport") or "football"),
        "event": event_name,
        "competition": fixture.get("league") or "E0",
        "date": fixture.get("date"),
        "commence_time": fixture.get("commence_time"),
        "market": (analysis or {}).get("market_type") or "aucun marché demandé",
        "decision": decision,
        "reasons": list(dict.fromkeys(reasons)),
        "probabilities": probabilities,
        "probability_diagnostics": diagnostics,
        "expected_goals": fixture.get("expected_goals"),
        "model_version": row.get("model_version"),
        "model_freshness": fixture.get("model_freshness"),
        "coverage_mode": coverage_mode,
        "cold_start_teams": cold_start_teams,
        "cold_start_model_weight": cold_start_model_weight,
        "market_eligible": bool(fixture.get("market_eligible", False)) and coverage_mode != "cold_start_league_priors",
        "winamax_odds": bool(analysis),
        "market_analysis": analysis,
        "prediction_id": row.get("id"),
        "provider_event_id": row.get("provider_event_id"),
    }


def _generate_daily_model_predictions(requested: str, *, horizon_days: int) -> dict[str, Any]:
    started = datetime.now(ZoneInfo("UTC"))
    try:
        source = fixture_source()
        if hasattr(source, "fetch_window"):
            snapshot = source.fetch_window(
                requested_date=requested, horizon_days=horizon_days, allow_network=True,
            )
        else:  # compatibility for injected tests and legacy sources
            snapshot = source.fetch(force=False, allow_network=True)
    except DailyFixtureError as exc:
        try:
            record_sync_run(
                job_name="daily_model_only", sport_key=f"soccer_epl:{requested}", status="error",
                fetched_events=0, inserted_snapshots=0, quota_remaining=None, quota_last_cost=0,
                error_message=type(exc).__name__, started_at=started,
            )
        except Exception:
            pass
        return {
            "status": "fixture_source_unavailable",
            "error": str(exc),
            "source": "zero-credit fixture sources",
            "credits_consumed": 0,
            "generated": [],
            "unsupported": [],
            "fixture_snapshot": None,
        }
    window = select_fixture_window(
        snapshot.fixtures,
        requested_date=requested,
        horizon_days=horizon_days,
        leagues=("E0",),
    )
    current = resources()
    history = current["football"]
    known_teams = set(history["home_team"].astype(str)) | set(history["away_team"].astype(str))
    generated: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    created = 0
    reused = 0
    cold_start = 0
    for item in window.to_dict(orient="records"):
        source_home = str(item["home_team"])
        source_away = str(item["away_team"])
        home = football_model_name(source_home)
        away = football_model_name(source_away)
        commence = pd.to_datetime(item["date"], utc=True)
        fixture_date = commence.date().isoformat()
        if commence <= pd.Timestamp.now(tz="UTC"):
            unsupported.append({
                "event": f"{source_home} — {source_away}",
                "date": fixture_date,
                "commence_time": commence.isoformat(),
                "reason": "rencontre déjà commencée : prédiction pré-match non générée",
            })
            continue
        missing = [team for team in (home, away) if team not in known_teams]
        try:
            prediction = _football_model_only_prediction(
                home_team=home,
                away_team=away,
                date=fixture_date,
                league=str(item["league"]),
                allow_cold_start=True,
            )
        except HTTPException as exc:
            unsupported.append({
                "event": f"{source_home} — {source_away}",
                "date": fixture_date,
                "commence_time": commence.isoformat(),
                "reason": "prédiction modèle indisponible",
                "error_type": type(exc).__name__,
                "source_teams": [source_home, source_away],
            })
            continue
        cold_start += int(bool(missing))
        prediction["fixture"]["commence_time"] = commence.isoformat()
        prediction["fixture"]["source_home_team"] = source_home
        prediction["fixture"]["source_away_team"] = source_away
        prediction["fixture"]["fixture_source"] = snapshot.source
        prediction["fixture"]["fixture_snapshot_sha256"] = snapshot.sha256
        prediction["fixture"]["model_freshness"] = prediction.get("model_freshness")
        prediction["fixture"]["expected_goals"] = prediction.get("expected_goals")
        prediction["fixture"]["market_eligible"] = prediction.get("market_eligible", False)
        check = probability_diagnostics(prediction["probabilities"])
        if not check["valid"]:
            unsupported.append({
                "event": f"{home} — {away}", "date": fixture_date,
                "commence_time": commence.isoformat(),
                "reason": "probabilités invalides", "issues": check["issues"],
            })
            continue
        event_id = fixture_identifier(item)
        persisted = record_prediction_once(
            sport="football",
            model_version=str(prediction["model_version"]),
            fixture=prediction["fixture"],
            probabilities=prediction["probabilities"],
            market_analysis=None,
            decision="model_only",
            provider_event_id=event_id,
        )
        created += int(bool(persisted["created"]))
        reused += int(not bool(persisted["created"]))
        generated.append({**prediction, "prediction_id": persisted["id"], "provider_event_id": event_id})
    try:
        record_sync_run(
            job_name="daily_model_only", sport_key=f"soccer_epl:{requested}", status="ok",
            fetched_events=len(window), inserted_snapshots=0,
            quota_remaining=None, quota_last_cost=0, started_at=started,
        )
    except Exception:
        pass
    return {
        "status": "ok",
        "source": snapshot.source,
        "credits_consumed": 0,
        "generated": generated,
        "unsupported": unsupported,
        "created": created,
        "reused": reused,
        "cold_start": cold_start,
        "fixture_snapshot": {
            "fetched_at": snapshot.fetched_at,
            "from_cache": snapshot.from_cache,
            "sha256": snapshot.sha256,
            "fixtures_in_window": len(window),
        },
    }


def _recent_daily_sync(requested: str) -> dict[str, Any] | None:
    expected_key = f"soccer_epl:{requested}"
    maximum_age = pd.Timedelta(hours=SETTINGS.daily_fixture_cache_hours)
    now = pd.Timestamp.now(tz="UTC")
    for row in recent_sync_runs(100):
        if row.get("job_name") != "daily_model_only" or row.get("sport_key") != expected_key:
            continue
        started = pd.to_datetime(row.get("started_at"), utc=True, errors="coerce")
        if not pd.isna(started) and now - started <= maximum_age:
            return row
    return None


def _daily_slate_payload(
    requested: str,
    *,
    horizon_days: int | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    horizon = SETTINGS.daily_fixture_horizon_days if horizon_days is None else max(0, min(31, int(horizon_days)))
    bundled = DAILY_SLATE / f"{requested}.json"
    rows = predictions_for_date(requested)
    existing_upcoming_rows: list[dict[str, Any]] = []
    for offset in range(1, horizon + 1):
        date_value = (pd.Timestamp(requested) + pd.Timedelta(days=offset)).date().isoformat()
        existing_upcoming_rows.extend(predictions_for_date(date_value))
    generation: dict[str, Any] | None = None
    if bundled.exists() and not rows:
        payload = json.loads(bundled.read_text(encoding="utf-8"))
        payload["source"] = "bundled_snapshot"
        payload["model_diagnostics"] = _model_diagnostics_payload()
        payload["credit_firewall"] = {"credits_consumed": 0, "daily_odds_enabled": SETTINGS.daily_odds_enabled}
        return payload
    recent_sync = _recent_daily_sync(requested)
    should_refresh = bool(refresh or (not rows and not existing_upcoming_rows and recent_sync is None))
    if should_refresh:
        generation = _generate_daily_model_predictions(requested, horizon_days=horizon)
    else:
        generation = {
            "status": "cached_predictions" if rows or existing_upcoming_rows else "recent_empty_refresh",
            "source": "postgresql",
            "credits_consumed": 0,
            "generated": [],
            "unsupported": [],
            "recent_sync": recent_sync,
        }
    rows = predictions_for_date(requested)
    today_events = [_daily_event_from_prediction(row) for row in rows]
    upcoming_rows: list[dict[str, Any]] = []
    for offset in range(1, horizon + 1):
        date_value = (pd.Timestamp(requested) + pd.Timedelta(days=offset)).date().isoformat()
        upcoming_rows.extend(predictions_for_date(date_value))
    upcoming_events = [_daily_event_from_prediction(row) for row in upcoming_rows]
    candidates = sum(event["decision"] == "candidat recherche" for event in today_events)
    valid_predictions = sum(bool(event["probability_diagnostics"]["valid"]) for event in today_events)
    cold_start_predictions = sum(event.get("coverage_mode") == "cold_start_league_priors" for event in today_events + upcoming_events)
    no_shortlist_reasons: list[str] = []
    generation_status = str((generation or {}).get("status") or "not_needed")
    if generation_status == "fixture_source_unavailable":
        no_shortlist_reasons.append("calendrier gratuit indisponible : aucune dépense de crédit n’a été engagée")
    elif not today_events:
        no_shortlist_reasons.append(f"aucun match E0 couvert par le modèle à cette date dans l’horizon de {horizon} jour(s)")
    unsupported_count = len((generation or {}).get("unsupported") or [])
    if unsupported_count:
        no_shortlist_reasons.append(f"{unsupported_count} rencontre(s) ignorée(s) pour cause de calendrier ou de prédiction invalide")
    if cold_start_predictions:
        no_shortlist_reasons.append(
            f"{cold_start_predictions} prédiction(s) utilisent des priors de championnat pour des clubs sans historique récent"
        )
    if today_events and not any(event["winamax_odds"] for event in today_events):
        no_shortlist_reasons.append("cotes payantes désactivées : probabilités modèle uniquement")
    if candidates == 0:
        no_shortlist_reasons.append("aucun avantage de marché robuste validé")
    if generation_status == "fixture_source_unavailable":
        fixture_status = "unavailable"
    elif today_events or upcoming_events:
        fixture_status = "available"
    elif generation_status in {"ok", "cached_predictions", "recent_empty_refresh"}:
        fixture_status = "no_fixtures"
    else:
        fixture_status = "unknown"
    return {
        "date": requested,
        "source": "postgresql" if rows or upcoming_rows else (generation or {}).get("status", "empty"),
        "fixture_status": fixture_status,
        "bookmaker": None,
        "summary": {
            "fixtures_today": len(today_events),
            "events_reviewed": len(today_events),
            "model_predictions": valid_predictions,
            "research_candidates": candidates,
            "abstentions": len(today_events) - candidates,
            "upcoming_predictions": len(upcoming_events),
            "cold_start_predictions": cold_start_predictions,
            "credits_consumed": int((generation or {}).get("credits_consumed") or 0),
        },
        "events": today_events,
        "upcoming_events": upcoming_events[:30],
        "unsupported_events": (generation or {}).get("unsupported", []),
        "generation": generation,
        "model_diagnostics": _model_diagnostics_payload(),
        "credit_firewall": {
            "model_only_cost_credits": 0,
            "daily_odds_enabled": SETTINGS.daily_odds_enabled,
            "daily_odds_max_credits": SETTINGS.daily_odds_max_credits,
            "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
        },
        "no_shortlist_reasons": list(dict.fromkeys(no_shortlist_reasons)),
        "warning": (
            "Probabilités de recherche uniquement. Les cotes sont facultatives et désactivées par défaut. "
            "Aucune sélection ne constitue une consigne de pari."
        ),
    }


def _paris_event_date(value: Any) -> str | None:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.tz_convert("Europe/Paris").date().isoformat()


def _infer_tennis_surface(*, sport_key: str, title: str = "") -> str:
    value = f"{sport_key} {title}".casefold()
    grass = ("wimbledon", "queens", "queen's", "halle", "eastbourne", "s-hertogenbosch", "newport")
    clay = (
        "roland", "french_open", "monte_carlo", "madrid", "rome", "roma", "barcelona", "munich",
        "hamburg", "kitzbuhel", "gstaad", "bastad", "umag", "geneva", "lyon", "estoril",
    )
    if any(token in value for token in grass):
        return "grass"
    if any(token in value for token in clay):
        return "clay"
    return "hard"


def _safe_current_signal(
    event: dict[str, Any], *, roi_lab: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    analysis = event.get("market_analysis") or {}
    selections = list(analysis.get("selections") or [])
    if not selections:
        return None
    model = event.get("model") or {}
    coverage = model.get("coverage_mode") or model.get("model_mode")
    if coverage == "cold_start_league_priors":
        return None

    sport = str(model.get("sport") or ("tennis" if str(event.get("sport_key", "")).startswith("tennis_") else "football"))
    optimisation = (roi_lab or {}).get("optimisation") or {}
    policy_payload = optimisation.get("policy") or SignalPolicy().to_dict()
    try:
        policy = SignalPolicy(**policy_payload)
    except (TypeError, ValueError):
        policy = SignalPolicy()
    meta = (roi_lab or {}).get("meta_model") or {}
    meta_sport_events = int((meta.get("sport_event_counts") or {}).get(sport) or 0)
    meta_ready = str(meta.get("status") or "") == "candidate" and meta_sport_events >= 30
    if model.get("market_eligible") is False and not meta_ready:
        return None

    shortlist = {str(item) for item in (analysis.get("shortlist") or [])}
    candidate_rows = [item for item in selections if str(item.get("selection")) in shortlist]
    if not candidate_rows and meta_ready:
        # A validated meta-model may rehabilitate a base model that abstained,
        # but only after at least 30 settled events for the same sport.
        candidate_rows = selections
    if not candidate_rows:
        return None

    scored: list[dict[str, Any]] = []
    for selected in candidate_rows:
        try:
            decimal_odds = float(selected["decimal_odds"])
            base_probability = float(selected["model_probability"])
            market_probability = float(selected["market_probability"])
            base_edge = float(selected["edge"])
            base_robust_return = float(selected["robust_expected_return"])
        except (KeyError, TypeError, ValueError):
            continue
        meta_probability = score_roi_meta_model(
            model_probability=base_probability,
            market_probability=market_probability,
            edge=base_edge,
            robust_expected_return=base_robust_return,
            decimal_odds=decimal_odds,
            sport=sport,
            meta_model=meta if meta_ready else {},
        )
        effective_probability = meta_probability if meta_probability is not None else base_probability
        effective_edge = effective_probability - market_probability
        effective_robust_return = max(0.001, effective_probability - 0.05) * decimal_odds - 1.0
        if effective_edge < policy.minimum_edge:
            continue
        if effective_robust_return < policy.minimum_robust_return:
            continue
        if decimal_odds > policy.maximum_decimal_odds:
            continue
        scored.append({
            "selected": selected,
            "decimal_odds": decimal_odds,
            "base_probability": base_probability,
            "market_probability": market_probability,
            "base_edge": base_edge,
            "base_robust_return": base_robust_return,
            "meta_probability": meta_probability,
            "effective_probability": effective_probability,
            "effective_edge": effective_edge,
            "effective_robust_return": effective_robust_return,
        })
    if not scored:
        return None
    best = max(scored, key=lambda row: (row["effective_robust_return"], row["effective_edge"]))
    selected = best["selected"]
    return {
        "sport": sport,
        "event_id": event.get("event_id"),
        "commence_time": event.get("commence_time"),
        "event": (
            f"{event.get('model_home_team') or event.get('api_home_team')} – {event.get('model_away_team') or event.get('api_away_team')}"
            if event.get("api_home_team")
            else f"{event.get('model_player_1') or event.get('api_player_1')} – {event.get('model_player_2') or event.get('api_player_2')}"
        ),
        "selection": str(selected.get("selection") or ""),
        "decimal_odds": best["decimal_odds"],
        "model_probability": best["base_probability"],
        "meta_probability": best["meta_probability"],
        "effective_probability": best["effective_probability"],
        "market_probability": best["market_probability"],
        "edge": best["effective_edge"],
        "robust_expected_return": best["effective_robust_return"],
        "base_edge": best["base_edge"],
        "base_robust_expected_return": best["base_robust_return"],
        "status": "SHADOW_SIGNAL_META" if best["meta_probability"] is not None else "SHADOW_SIGNAL_PRE_MODEL",
        "policy_source": "chronological_roi_policy" if optimisation.get("status") == "candidate" else "pre_registered_default",
        "meta_sport_events": meta_sport_events,
        "research_only": True,
    }


def _research_learning_report(roi: Mapping[str, Any]) -> dict[str, Any]:
    champion = latest_model_decision("dual_sport_research")
    return build_champion_challenger_report(
        roi,
        champion=champion,
        minimum_events=SETTINGS.research_promotion_min_events,
        minimum_holdout_signals=SETTINGS.research_promotion_min_holdout_signals,
        maximum_drawdown=SETTINGS.research_promotion_max_drawdown,
        minimum_events_per_sport=SETTINGS.research_promotion_min_events_per_sport,
    )


def _research_automation_status(*, requested_date: str | None = None) -> dict[str, Any]:
    date = requested_date or datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    budget = research_credits_consumed_on(date)
    remaining = max(0, int(SETTINGS.daily_odds_max_credits) - int(budget["credits_consumed"]))
    due = due_shadow_events(limit=500)
    enabled = bool(SETTINGS.automated_shadow_enabled)
    if not enabled:
        next_action = "Automation is off. The model-only daily product remains available at zero credits."
    elif not SETTINGS.daily_odds_enabled or not SETTINGS.shadow_enabled:
        next_action = "Enable both DAILY_ODDS_ENABLED and SHADOW_MODE_ENABLED before the automated cycle can capture evidence."
    elif remaining <= 0:
        next_action = "The daily provider budget is exhausted; wait for the next local day."
    elif due:
        next_action = "Settle due shadow events before considering another capture."
    else:
        next_action = "The automated shadow cycle may capture one bounded snapshot when scheduled."
    return {
        "enabled": enabled,
        "daily_odds_enabled": bool(SETTINGS.daily_odds_enabled),
        "shadow_enabled": bool(SETTINGS.shadow_enabled),
        "date": date,
        "daily_credit_cap": int(SETTINGS.daily_odds_max_credits),
        "credits_consumed": int(budget["credits_consumed"]),
        "credits_remaining": int(remaining),
        "cost_runs": budget["runs"],
        "due_events": len(due),
        "capture_allowed": bool(enabled and SETTINGS.daily_odds_enabled and SETTINGS.shadow_enabled and remaining > 0),
        "next_action": next_action,
        "automatic_bet_placement": False,
    }


def _research_report_from_slates(
    *, requested_date: str, football: dict[str, Any] | None,
    tennis: list[dict[str, Any]], credits_consumed: int, errors: list[dict[str, str]],
) -> dict[str, Any]:
    football_events = [
        item for item in ((football or {}).get("events") or [])
        if _paris_event_date(item.get("commence_time")) == requested_date
    ]
    tennis_events: list[dict[str, Any]] = []
    for slate in tennis:
        tennis_events.extend(
            item for item in (slate.get("events") or [])
            if _paris_event_date(item.get("commence_time")) == requested_date
        )
    settled_rows = recent_shadow_predictions(10000, status="settled")
    roi = build_roi_lab_report(settled_rows)
    learning = _research_learning_report(roi)
    automation = _research_automation_status(requested_date=requested_date)
    signals = [
        signal for signal in (
            _safe_current_signal(item, roi_lab=roi) for item in [*football_events, *tennis_events]
        )
        if signal is not None
    ]
    optimisation = roi.get("optimisation") or {}
    training_status = optimisation.get("status") or "not_evaluable"
    return {
        "date": requested_date,
        "mode": "dual_sport_shadow_research",
        "football": {
            "events": football_events,
            "summary": (football or {}).get("summary") or {},
            "from_cache": (football or {}).get("from_cache"),
        },
        "tennis": {
            "events": tennis_events,
            "tournaments": [
                {
                    "sport_key": slate.get("sport_key"),
                    "surface": slate.get("surface"),
                    "summary": slate.get("summary") or {},
                    "from_cache": slate.get("from_cache"),
                }
                for slate in tennis
            ],
        },
        "signals": signals,
        "summary": {
            "football_matches": len(football_events),
            "tennis_matches": len(tennis_events),
            "experimental_signals": len(signals),
            "credits_consumed": int(credits_consumed),
            "settled_market_events": int(roi.get("unique_events") or 0),
            "roi_policy_status": training_status,
            "learning_status": learning.get("status"),
        },
        "roi_lab": roi,
        "learning": learning,
        "automation": automation,
        "errors": errors,
        "constraints": {
            "automatic_bet_placement": False,
            "real_money_stake_recommendation": False,
            "signals_are_experimental": True,
            "cold_start_market_signals_allowed": False,
        },
        "next_action": (
            "Collect and settle at least 30 temporally valid market events before treating ROI optimisation as evaluable."
            if training_status == "not_evaluable"
            else "Keep the policy in shadow and review its untouched chronological holdout before any status change."
        ),
    }


def _active_tennis_sports(*, requested: list[str], maximum: int) -> list[dict[str, str]]:
    if maximum <= 0:
        return []
    if requested:
        return [{"key": key, "title": key} for key in requested[:maximum]]
    configured = list(SETTINGS.daily_tennis_sport_keys)
    if configured:
        return [{"key": key, "title": key} for key in configured[:maximum]]
    response = odds_client().list_sports(
        include_inactive=False,
        allow_network=SETTINGS.daily_odds_enabled and SETTINGS.daily_odds_max_credits >= 1,
    )
    candidates = []
    for item in response.payload if isinstance(response.payload, list) else []:
        key = str(item.get("key") or "")
        group = str(item.get("group") or "")
        title = str(item.get("title") or key)
        lowered = f"{key} {title}".casefold()
        if not key.startswith("tennis_") or group.casefold() != "tennis":
            continue
        if any(token in lowered for token in ("winner", "outright", "doubles")):
            continue
        candidates.append({"key": key, "title": title})
    candidates.sort(key=lambda item: ("atp" not in item["key"], "wta" not in item["key"], item["title"]))
    return candidates[:maximum]


def _latest_research_payload() -> dict[str, Any]:
    latest = latest_benchmark_run("dual_sport_daily")
    settled_rows = recent_shadow_predictions(10000, status="settled")
    roi = build_roi_lab_report(settled_rows)
    learning = _research_learning_report(roi)
    today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    automation = _research_automation_status(requested_date=today)
    if latest and latest.get("report"):
        payload = dict(latest["report"])
        payload["roi_lab"] = roi
        payload["learning"] = learning
        payload["automation"] = automation
        payload["summary"] = {
            **(payload.get("summary") or {}),
            "settled_market_events": int(roi.get("unique_events") or 0),
            "roi_policy_status": str((roi.get("optimisation") or {}).get("status") or "not_evaluable"),
            "learning_status": learning.get("status"),
        }
        payload["run"] = {
            "id": latest.get("id"),
            "status": latest.get("status"),
            "started_at": latest.get("started_at"),
            "finished_at": latest.get("finished_at"),
        }
        return payload
    return {
        "date": today,
        "mode": "dual_sport_shadow_research",
        "football": {"events": [], "summary": {}},
        "tennis": {"events": [], "tournaments": []},
        "signals": [],
        "summary": {
            "football_matches": 0,
            "tennis_matches": 0,
            "experimental_signals": 0,
            "credits_consumed": 0,
            "settled_market_events": int(roi.get("unique_events") or 0),
            "roi_policy_status": str((roi.get("optimisation") or {}).get("status") or "not_evaluable"),
            "learning_status": learning.get("status"),
        },
        "roi_lab": roi,
        "learning": learning,
        "automation": automation,
        "errors": [],
        "constraints": {
            "automatic_bet_placement": False,
            "real_money_stake_recommendation": False,
            "signals_are_experimental": True,
        },
        "next_action": automation["next_action"],
        "run": None,
    }


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
        "daily_model_only_enabled": True,
        "daily_odds_enabled": SETTINGS.daily_odds_enabled,
        "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
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
        "daily_model_only_enabled": True,
        "daily_odds_enabled": SETTINGS.daily_odds_enabled,
        "daily_odds_max_credits": SETTINGS.daily_odds_max_credits,
        "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
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
    today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    daily_rows = predictions_for_date(today)
    daily_diagnostics = _model_diagnostics_payload()
    daily_run = next((row for row in recent_sync_runs(50) if row.get("job_name") == "daily_model_only"), None)
    fixture_status = "predictions_available" if daily_rows else "not_refreshed"
    if not daily_rows and daily_run and str(daily_run.get("status")) == "ok":
        fixture_status = "no_fixtures" if int(daily_run.get("fetched_events") or 0) == 0 else "refreshed_without_supported_predictions"
    return build_control_center(
        release=status.get("release") or {},
        database=status.get("database") or {},
        models=status.get("models") or [],
        shadow_cycle=((status.get("shadow") or {}).get("latest_cycle")),
        benchmark=status.get("benchmark") or {},
        model_decision=status.get("model_decision") or {},
        backfills=recent_backfill_jobs(limit=10),
        daily_product={
            "model_status": daily_diagnostics.get("status"),
            "prediction_count": len(daily_rows),
            "fixture_status": fixture_status,
            "shadow_enabled": SETTINGS.shadow_enabled,
            "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
        },
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


@app.get("/api/model-diagnostics")
def model_diagnostics() -> dict[str, Any]:
    return _model_diagnostics_payload()


@app.get("/api/daily/slate")
def daily_slate(
    date: str | None = None,
    horizon_days: int | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    requested = date or datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    if not DATE_RE.fullmatch(requested):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    if horizon_days is not None and not 0 <= horizon_days <= 31:
        raise HTTPException(status_code=422, detail="horizon_days must be between 0 and 31")
    return _daily_slate_payload(requested, horizon_days=horizon_days, refresh=refresh)



def _challenger_factory_artifact() -> dict[str, Any]:
    latest = latest_benchmark_run("sport_challenger_factory")
    if latest and isinstance(latest.get("report"), dict):
        return {**latest["report"], "run": {"id": latest.get("id"), "status": latest.get("status")}}
    path = ROOT / "artifacts" / "challenger_factory_v4_9.json"
    if not path.exists():
        return {
            "schema_version": "1.0",
            "status": "not_run",
            "sports": {
                "football": {"status": "not_run", "reason": "run_challenger_factory"},
                "tennis": {"status": "not_run", "reason": "run_challenger_factory"},
            },
            "limits": {"provider_credits_consumed": 0, "automatic_promotion": False},
            "next_action": "Run the zero-credit challenger factory from the protected workflow.",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema_version": "1.0", "status": "invalid_artifact",
            "sports": {},
            "limits": {"provider_credits_consumed": 0, "automatic_promotion": False},
            "next_action": "Regenerate the challenger factory artifact.",
        }
    return payload


def _evidence_acceleration_artifact() -> dict[str, Any]:
    latest = latest_benchmark_run("dual_sport_evidence_acceleration")
    if latest and isinstance(latest.get("report"), dict):
        return {**latest["report"], "run": {"id": latest.get("id"), "status": latest.get("status")}}
    path = ROOT / "artifacts" / "evidence_acceleration_v4_9.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "schema_version": "1.0",
        "status": "not_run",
        "football": {"status": "not_run", "reason": "run_evidence_acceleration"},
        "tennis": {
            "catalog": {"readiness": {"status": "collecting"}, "rows": 0, "distinct_dates": 0},
            "holdout_generation": {"status": "open_collecting"},
        },
        "limits": {"provider_credits_consumed": 0, "automatic_promotion": False},
        "next_action": "Run the zero-credit evidence acceleration workflow.",
    }


def _controlled_model_decision_artifact() -> dict[str, Any]:
    latest = latest_benchmark_run("controlled_model_decision")
    if latest and isinstance(latest.get("report"), dict):
        return {**latest["report"], "run": {"id": latest.get("id"), "status": latest.get("status")}}
    path = ROOT / "artifacts" / "controlled_model_decision_v4_9.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "schema_version": "1.0",
        "status": "not_run",
        "football": {"status": "not_run", "challengers": [], "promotion_ready": False},
        "tennis": {
            "training_status": "blocked_below_readiness_gates",
            "progress": {
                "exploratory_rows": {"actual": 0, "required": 500},
                "exploratory_dates": {"actual": 0, "required": 50},
            },
        },
        "production_validation": {"status": "not_proven"},
        "limits": {"provider_credits_consumed": 0, "automatic_promotion": False},
        "next_action": "Run the protected controlled model decision workflow.",
    }


@app.get("/api/evidence-acceleration")
def evidence_acceleration() -> dict[str, Any]:
    return _evidence_acceleration_artifact()


@app.post("/api/evidence-acceleration/run")
def run_evidence_acceleration(req: EvidenceAccelerationRunRequest) -> dict[str, Any]:
    if req.confirmation != "RUN_EVIDENCE_ACCELERATION":
        raise HTTPException(status_code=409, detail="confirmation must equal RUN_EVIDENCE_ACCELERATION")
    report = build_evidence_acceleration_report(root=ROOT, source=req.source, license_status=req.license_status)
    report = json.loads(json.dumps(report, default=str))
    output = ROOT / "artifacts" / "evidence_acceleration_v4_9.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    catalog = report["tennis"]["catalog"]
    generation = report["tennis"]["holdout_generation"]
    catalog_id = register_dataset_catalog(catalog)
    generation_id = register_holdout_generation(generation)
    status = str(report.get("status") or "collecting")
    run_id = record_benchmark_run(
        sport_key="dual_sport_evidence_acceleration",
        model_version=APP_VERSION,
        status=status,
        config={
            "mode": "zero_credit_evidence_acceleration",
            "provider_calls": 0,
            "maximum_new_football_challengers": 2,
            "holdout_generations": True,
        },
        report=report,
        summary={
            "football_status": report["football"]["status"],
            "tennis_status": catalog["readiness"]["status"],
            "dataset_id": catalog["dataset_id"],
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
        },
    )
    return {**report, "run": {"id": run_id, "status": status}, "registry": {"dataset_catalog_record_id": catalog_id, "holdout_generation_record_id": generation_id}}


@app.get("/api/controlled-model-decision")
def controlled_model_decision() -> dict[str, Any]:
    return _controlled_model_decision_artifact()


@app.post("/api/controlled-model-decision/run")
def run_controlled_model_decision(req: ControlledModelDecisionRunRequest) -> dict[str, Any]:
    if req.confirmation != "RUN_CONTROLLED_MODEL_DECISION":
        raise HTTPException(status_code=409, detail="confirmation must equal RUN_CONTROLLED_MODEL_DECISION")
    report = build_controlled_model_decision_report(root=ROOT, app_version=APP_VERSION)
    report = json.loads(json.dumps(report, default=str))
    output = ROOT / "artifacts" / "controlled_model_decision_v4_9.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    consulted_id = register_holdout_generation(report["football"]["consulted_holdout_generation"])
    promotion_id = register_holdout_generation(report["football"]["promotion_holdout_generation"])
    status = str(report.get("status") or "collecting")
    run_id = record_benchmark_run(
        sport_key="controlled_model_decision",
        model_version=APP_VERSION,
        status=status,
        config={
            "mode": "bounded_controlled_model_decision",
            "provider_calls": 0,
            "maximum_football_challengers": 2,
            "promotion_holdout_required": True,
        },
        report=report,
        summary={
            "football_status": report["football"]["status"],
            "tennis_status": report["tennis"]["training_status"],
            "production_validation": report["production_validation"]["status"],
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
        },
    )
    return {
        **report,
        "run": {"id": run_id, "status": status},
        "registry": {
            "consulted_holdout_record_id": consulted_id,
            "promotion_holdout_record_id": promotion_id,
        },
    }


@app.get("/api/challenger-factory")
def challenger_factory() -> dict[str, Any]:
    """Read the last zero-credit sport challenger evaluation artifact."""
    return _challenger_factory_artifact()


@app.post("/api/challenger-factory/run")
def run_challenger_factory(req: ChallengerFactoryRunRequest) -> dict[str, Any]:
    if req.confirmation != "RUN_CHALLENGER_FACTORY":
        raise HTTPException(status_code=409, detail="confirmation must equal RUN_CHALLENGER_FACTORY")
    report = build_challenger_factory_report(root=ROOT)
    output = ROOT / "artifacts" / "challenger_factory_v4_9.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    status = str(report.get("status") or "collecting")
    run_id = record_benchmark_run(
        sport_key="sport_challenger_factory",
        model_version=APP_VERSION,
        status=status,
        config={
            "mode": "bounded_sport_challenger_factory",
            "provider_calls": 0,
            "maximum_models_per_sport": ((report.get("limits") or {}).get("maximum_models_per_sport")),
        },
        report=report,
        summary={
            "football_status": ((report.get("sports") or {}).get("football") or {}).get("status"),
            "tennis_status": ((report.get("sports") or {}).get("tennis") or {}).get("status"),
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
        },
    )
    return {**report, "run": {"id": run_id, "status": status}}


@app.get("/api/feature-lab")
def feature_lab() -> dict[str, Any]:
    """Evaluate bounded per-sport calibration with no provider calls."""
    rows = recent_shadow_predictions(10000, status="settled")
    return build_feature_lab_report(rows)


@app.post("/api/feature-lab/run")
def run_feature_lab(req: FeatureLabRunRequest) -> dict[str, Any]:
    if req.confirmation != "RUN_FEATURE_LAB":
        raise HTTPException(status_code=409, detail="confirmation must equal RUN_FEATURE_LAB")
    rows = recent_shadow_predictions(10000, status="settled")
    report = build_feature_lab_report(rows)
    status = "completed" if report.get("status") == "ready" else "collecting"
    run_id = record_benchmark_run(
        sport_key="dual_sport_feature_lab",
        model_version=APP_VERSION,
        status=status,
        config={
            "mode": "bounded_calibration_feature_lab",
            "provider_calls": 0,
            "maximum_experiments_per_sport": 12,
            "maximum_calibrators_per_sport": 4,
        },
        report=report,
        summary={
            "overall_reliability": report.get("overall_reliability"),
            "football_status": ((report.get("sports") or {}).get("football") or {}).get("status"),
            "tennis_status": ((report.get("sports") or {}).get("tennis") or {}).get("status"),
            "provider_credits_consumed": 0,
        },
    )
    return {**report, "run": {"id": run_id, "status": status}}


@app.get("/api/research-lab")
def research_lab() -> dict[str, Any]:
    """Return the latest persisted dual-sport market research report.

    This endpoint never calls the paid provider. Only the explicit POST refresh
    endpoint or its protected workflow may create a new market snapshot.
    """
    return _latest_research_payload()


@app.post("/api/research-lab/optimise")
def optimise_research_policy() -> dict[str, Any]:
    settled = settle_shadow_predictions()
    rows = recent_shadow_predictions(10000, status="settled")
    roi = build_roi_lab_report(rows)
    learning = _research_learning_report(roi)
    previous = _latest_research_payload()
    report = {
        **previous,
        "roi_lab": roi,
        "learning": learning,
        "automation": _research_automation_status(),
        "summary": {
            **(previous.get("summary") or {}),
            "settled_market_events": int(roi.get("unique_events") or 0),
            "roi_policy_status": str((roi.get("optimisation") or {}).get("status") or "not_evaluable"),
            "learning_status": learning.get("status"),
        },
        "settlement": settled,
    }
    status = "completed" if (roi.get("optimisation") or {}).get("status") == "candidate" else "not_evaluable"
    run_id = record_benchmark_run(
        sport_key="dual_sport_daily",
        model_version=APP_VERSION,
        status=status,
        config={"mode": "roi_policy_optimisation", "provider_calls": 0},
        report=report,
        summary=report.get("summary"),
    )
    return {**report, "run": {"id": run_id, "status": status}}


@app.get("/api/research-lab/learning")
def research_learning() -> dict[str, Any]:
    payload = _latest_research_payload()
    return {
        "learning": payload.get("learning"),
        "automation": payload.get("automation"),
        "summary": payload.get("summary"),
        "constraints": payload.get("constraints"),
        "challenger_factory": _challenger_factory_artifact(),
        "evidence_acceleration": _evidence_acceleration_artifact(),
    }


@app.post("/api/research-lab/champion/promote")
def promote_research_champion(req: ResearchChampionPromotionRequest) -> dict[str, Any]:
    if req.confirmation != "PROMOTE_RESEARCH_CHAMPION":
        raise HTTPException(status_code=409, detail="confirmation must equal PROMOTE_RESEARCH_CHAMPION")
    payload = _latest_research_payload()
    learning = payload.get("learning") or {}
    if str(learning.get("candidate_id") or "") != req.candidate_id:
        raise HTTPException(status_code=409, detail="candidate_id no longer matches the current challenger")
    if not bool(learning.get("promotion_allowed")):
        raise HTTPException(status_code=409, detail="challenger has not passed all promotion gates")
    decision = {
        "status": "approved",
        "candidate": learning.get("candidate"),
        "gates": learning.get("gates"),
        "comparison": learning.get("comparison"),
        "roi_lab": payload.get("roi_lab"),
        "approved_at": datetime.now(ZoneInfo("Europe/Paris")).isoformat(),
        "approval_note": req.note,
        "manual_approval": True,
        "automatic_promotion": False,
        "automatic_bet_placement": False,
    }
    decision_id = record_model_decision(
        sport_key="dual_sport_research",
        champion=req.candidate_id,
        decision=decision,
        benchmark_run_id=(payload.get("run") or {}).get("id"),
    )
    return {
        "status": "approved",
        "decision_id": decision_id,
        "champion": req.candidate_id,
        "automatic_promotion": False,
        "automatic_bet_placement": False,
    }


@app.post("/api/research-lab/refresh")
def refresh_research_lab(req: DailyResearchRefreshRequest) -> dict[str, Any]:
    if req.confirmation != "CAPTURE_DAILY_MARKET":
        raise HTTPException(status_code=409, detail="confirmation must equal CAPTURE_DAILY_MARKET")
    if req.automation and not SETTINGS.automated_shadow_enabled:
        raise HTTPException(status_code=409, detail="AUTOMATED_SHADOW_ENABLED is false")
    if not SETTINGS.daily_odds_enabled:
        raise HTTPException(status_code=409, detail="DAILY_ODDS_ENABLED is false")
    if SETTINGS.daily_odds_max_credits < 1:
        raise HTTPException(status_code=409, detail="DAILY_ODDS_MAX_CREDITS must be at least 1")
    if not SETTINGS.shadow_enabled:
        raise HTTPException(
            status_code=409,
            detail="SHADOW_MODE_ENABLED must be true so every paid snapshot becomes training evidence",
        )
    requested_date = req.date or datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    if not DATE_RE.fullmatch(requested_date):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    spent_before = research_credits_consumed_on(requested_date)
    remaining_daily = max(0, int(SETTINGS.daily_odds_max_credits) - int(spent_before["credits_consumed"]))
    hard_cap = min(int(req.max_credits), remaining_daily)
    if hard_cap < 1:
        raise HTTPException(status_code=409, detail="Daily research credit budget is exhausted")
    credits_consumed = 0
    errors: list[dict[str, str]] = []
    football_slate: dict[str, Any] | None = None
    tennis_slates: list[dict[str, Any]] = []

    # Automated runs consult the free fixture product first. This avoids paying
    # for an empty football market day. Manual research runs preserve the explicit
    # operator request and may probe the configured market directly.
    football_due = True
    if req.automation:
        try:
            free_slate = _daily_slate_payload(requested_date, horizon_days=0, refresh=False)
            football_due = int((free_slate.get("summary") or {}).get("fixtures_today") or 0) > 0
        except Exception as exc:  # free-source failure must not trigger a paid fallback
            football_due = False
            errors.append({"scope": "football_precheck", "error": type(exc).__name__})
    if hard_cap >= 1 and football_due:
        try:
            football_slate = _football_odds_slate("soccer_epl", "E0", force_refresh=False)
            if not football_slate.get("from_cache"):
                credits_consumed += int((football_slate.get("quota") or {}).get("last_cost") or 1)
        except HTTPException as exc:
            errors.append({"scope": "football", "error": str(exc.detail)})

    remaining = max(0, hard_cap - credits_consumed)
    tennis_limit = min(int(req.tennis_limit), int(SETTINGS.daily_tennis_max_tournaments), remaining)
    sports: list[dict[str, str]] = []
    if tennis_limit:
        try:
            sports = _active_tennis_sports(requested=req.tennis_sport_keys, maximum=tennis_limit)
        except (OddsApiError, OddsApiNotConfigured, OddsApiNetworkDisabled) as exc:
            errors.append({"scope": "tennis_discovery", "error": type(exc).__name__})
    for item in sports:
        if credits_consumed >= hard_cap:
            break
        key = item["key"]
        surface = _infer_tennis_surface(sport_key=key, title=item.get("title", ""))
        try:
            slate = _tennis_odds_slate(key, surface, force_refresh=False)
            tennis_slates.append(slate)
            if not slate.get("from_cache"):
                credits_consumed += int((slate.get("quota") or {}).get("last_cost") or 1)
        except HTTPException as exc:
            errors.append({"scope": key, "error": str(exc.detail)})
        if credits_consumed > hard_cap:
            errors.append({"scope": key, "error": "provider_cost_exceeded_daily_cap"})
            break

    if credits_consumed > hard_cap:
        raise HTTPException(status_code=503, detail="Provider reported a cost above the authorised daily cap")
    settlement = settle_shadow_predictions()
    report = _research_report_from_slates(
        requested_date=requested_date,
        football=football_slate,
        tennis=tennis_slates,
        credits_consumed=credits_consumed,
        errors=errors,
    )
    report["settlement"] = settlement
    report["credit_cap"] = hard_cap
    report["credit_budget"] = {
        "daily_cap": int(SETTINGS.daily_odds_max_credits),
        "spent_before": int(spent_before["credits_consumed"]),
        "spent_this_run": int(credits_consumed),
        "remaining_after": max(0, remaining_daily - int(credits_consumed)),
    }
    report["automation"] = {
        **(report.get("automation") or {}),
        "credits_consumed": int(spent_before["credits_consumed"]) + int(credits_consumed),
        "credits_remaining": max(0, remaining_daily - int(credits_consumed)),
    }
    report["shadow_recording_enabled"] = SETTINGS.shadow_enabled
    status = "completed" if not errors else "completed_with_warnings"
    run_id = record_benchmark_run(
        sport_key="dual_sport_daily",
        model_version=APP_VERSION,
        status=status,
        config={
            "mode": "daily_live_market_shadow",
            "date": requested_date,
            "max_credits": hard_cap,
            "tennis_limit": tennis_limit,
            "tennis_sport_keys": [item["key"] for item in sports],
            "automation": bool(req.automation),
        },
        report=report,
        summary=report.get("summary"),
        error_message=(json.dumps(errors, ensure_ascii=False)[:1000] if errors else None),
    )
    return {**report, "run": {"id": run_id, "status": status}}


@app.post("/api/research-lab/settle")
def settle_research_lab(req: DailyResearchSettleRequest) -> dict[str, Any]:
    if req.confirmation != "SETTLE_DAILY_MARKET":
        raise HTTPException(status_code=409, detail="confirmation must equal SETTLE_DAILY_MARKET")
    if req.automation and not SETTINGS.automated_shadow_enabled:
        raise HTTPException(status_code=409, detail="AUTOMATED_SHADOW_ENABLED is false")
    if not SETTINGS.daily_odds_enabled:
        raise HTTPException(status_code=409, detail="DAILY_ODDS_ENABLED is false")
    requested_date = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    spent_before = research_credits_consumed_on(requested_date)
    remaining_daily = max(0, int(SETTINGS.daily_odds_max_credits) - int(spent_before["credits_consumed"]))
    hard_cap = min(int(req.max_credits), remaining_daily)
    due = due_shadow_events(limit=500)
    if not due:
        settlement = settle_shadow_predictions()
        rows = recent_shadow_predictions(10000, status="settled")
        roi = build_roi_lab_report(rows)
        learning = _research_learning_report(roi)
        previous = _latest_research_payload()
        summary = {
            **(previous.get("summary") or {}),
            "credits_consumed": 0,
            "settled_market_events": int(roi.get("unique_events") or 0),
            "roi_policy_status": str((roi.get("optimisation") or {}).get("status") or "not_evaluable"),
            "learning_status": learning.get("status"),
        }
        report = {
            **previous,
            "summary": summary,
            "roi_lab": roi,
            "learning": learning,
            "automation": _research_automation_status(requested_date=requested_date),
            "settlement": {**settlement, "due_events": 0, "completed_seen": 0, "results_imported": 0, "credits_consumed": 0},
        }
        run_id = record_benchmark_run(
            sport_key="dual_sport_daily", model_version=APP_VERSION, status="completed",
            config={"mode": "daily_result_settlement", "max_credits": 0, "date": requested_date, "automation": bool(req.automation), "no_op": True},
            report=report, summary=summary,
        )
        return {**report, "run": {"id": run_id, "status": "completed"}}
    if hard_cap < 1:
        raise HTTPException(status_code=409, detail="Daily research credit budget is exhausted")

    grouped: dict[str, list[str]] = {}
    for item in due:
        grouped.setdefault(str(item["sport_key"]), []).append(str(item["provider_event_id"]))
    credits_consumed = 0
    imported = 0
    completed_seen = 0
    errors: list[dict[str, str]] = []
    for sport_key in sorted(grouped):
        if credits_consumed >= hard_cap:
            break
        try:
            response = odds_client().scores(
                sport_key,
                days_from=None,
                event_ids=grouped[sport_key],
                force_refresh=False,
            )
            if not response.from_cache:
                credits_consumed += int(response.quota.last_cost or 1)
            rows = normalize_scores_payload(response.payload)
            completed = rows[
                rows["completed"] & rows["home_score"].notna() & rows["away_score"].notna()
            ] if not rows.empty else rows
            completed_seen += len(completed)
            for row in completed.to_dict(orient="records"):
                try:
                    persist_event_result(
                        provider_event_id=str(row["event_id"]),
                        home_score=int(row["home_score"]),
                        away_score=int(row["away_score"]),
                        completed_at=row.get("last_update") or row["commence_time"],
                        source="the_odds_api_scores",
                    )
                    imported += 1
                except ValueError as exc:
                    record_data_quality_issue(
                        issue_type="score_without_known_event",
                        severity="warning",
                        provider_event_id=str(row.get("event_id") or "") or None,
                        details={"sport_key": sport_key, "reason": str(exc)},
                    )
        except (OddsApiError, OddsApiNotConfigured) as exc:
            errors.append({"scope": sport_key, "error": type(exc).__name__})
        if credits_consumed > hard_cap:
            raise HTTPException(status_code=503, detail="Provider reported a result-sync cost above the authorised cap")

    settlement = settle_shadow_predictions()
    rows = recent_shadow_predictions(10000, status="settled")
    roi = build_roi_lab_report(rows)
    learning = _research_learning_report(roi)
    previous = _latest_research_payload()
    summary = {
        **(previous.get("summary") or {}),
        "credits_consumed": int(credits_consumed),
        "settled_market_events": int(roi.get("unique_events") or 0),
        "roi_policy_status": str((roi.get("optimisation") or {}).get("status") or "not_evaluable"),
        "learning_status": learning.get("status"),
    }
    report = {
        **previous,
        "summary": summary,
        "roi_lab": roi,
        "learning": learning,
        "automation": {
            **_research_automation_status(requested_date=requested_date),
            "credits_consumed": int(spent_before["credits_consumed"]) + int(credits_consumed),
            "credits_remaining": max(0, remaining_daily - int(credits_consumed)),
        },
        "credit_budget": {
            "daily_cap": int(SETTINGS.daily_odds_max_credits),
            "spent_before": int(spent_before["credits_consumed"]),
            "spent_this_run": int(credits_consumed),
            "remaining_after": max(0, remaining_daily - int(credits_consumed)),
        },
        "settlement": {
            **settlement,
            "due_events": len(due),
            "completed_seen": int(completed_seen),
            "results_imported": int(imported),
            "credits_consumed": int(credits_consumed),
        },
        "errors": [*(previous.get("errors") or []), *errors],
    }
    status = "completed" if not errors else "completed_with_warnings"
    run_id = record_benchmark_run(
        sport_key="dual_sport_daily",
        model_version=APP_VERSION,
        status=status,
        config={"mode": "daily_result_settlement", "max_credits": hard_cap, "date": requested_date, "automation": bool(req.automation)},
        report=report,
        summary=summary,
        error_message=(json.dumps(errors, ensure_ascii=False)[:1000] if errors else None),
    )
    return {**report, "run": {"id": run_id, "status": status}}


@app.get("/api/bets/today")
def bets_today(date: str | None = None) -> dict[str, Any]:
    # Backward-compatible route. V4.3 no longer promises a bet: it returns the
    # daily fixture and model-probability product, with market enrichment only
    # when explicitly available.
    requested = date or datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    if not DATE_RE.fullmatch(requested):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    return _daily_slate_payload(requested)




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


@app.get("/api/credit-firewall")
def credit_firewall() -> dict[str, Any]:
    return {
        "status": "protected",
        "model_only_predictions_cost_credits": 0,
        "daily_odds_enabled": SETTINGS.daily_odds_enabled,
        "daily_odds_max_credits": SETTINGS.daily_odds_max_credits,
        "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
        "provider_cache_available": odds_client().config.cache_dir.exists(),
        "automatic_bet_placement": False,
        "automatic_model_promotion": False,
    }


@app.get("/api/odds/status")
def odds_status() -> dict[str, Any]:
    client = odds_client()
    db = database_summary()
    return {
        "provider": "The Odds API",
        "configured": client.config.configured,
        "paid_calls_enabled": SETTINGS.daily_odds_enabled,
        "daily_credit_cap": SETTINGS.daily_odds_max_credits,
        "historical_evidence_enabled": SETTINGS.historical_evidence_enabled,
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
        response = odds_client().list_sports(
            allow_network=SETTINGS.daily_odds_enabled and SETTINGS.daily_odds_max_credits >= 1
        )
    except OddsApiNetworkDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
