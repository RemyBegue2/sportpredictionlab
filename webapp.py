from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import json
import re

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from sports_predictor.artifacts import verify_artifact_manifest
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
    record_prediction,
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

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DAILY_SLATE = ROOT / "data" / "daily_slate"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SPORT_KEY_RE = re.compile(r"^[a-z0-9_\-]+$")
ODDS_BOOKMAKERS = ("winamax_fr", "betclic_fr", "unibet_fr", "pmu_fr", "netbet_fr", "pinnacle")
SPORT_LEAGUE_MAP = {"soccer_epl": "E0"}
SETTINGS = CloudSettings.from_env(ROOT)
STARTUP_STATE: dict[str, str | None] = {"database_error": None, "model_error": None}


def initialize_runtime() -> None:
    try:
        init_database(SETTINGS)
        STARTUP_STATE["database_error"] = None
    except Exception as exc:  # readiness reports the failure without exposing credentials
        STARTUP_STATE["database_error"] = type(exc).__name__
    try:
        resources()
        STARTUP_STATE["model_error"] = None
    except Exception as exc:
        STARTUP_STATE["model_error"] = type(exc).__name__


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_runtime()
    yield


app = FastAPI(
    title="Sports Prediction Lab V3.1 Cloud",
    version="3.1.0",
    description="Authenticated cloud edition with PostgreSQL persistence, scheduled odds synchronization and market-aware research.",
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
    football = pd.read_csv(ROOT / "data/real_snapshot/football_epl_2023_24_snapshot.csv")
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
    return {
        "football": football,
        "tennis": tennis,
        "football_model": football_model,
        "tennis_model": tennis_model,
        "metrics": metrics,
        "backtest": backtest,
        "provenance": provenance,
        "artifact_manifest": artifact_manifest,
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
            model_version=SETTINGS.model_version,
            fixture=payload["fixture"],
            probabilities=payload["probabilities"],
            market_analysis=analysis,
            decision=decision,
            provider_event_id=provider_event_id,
        )
    except Exception as exc:
        STARTUP_STATE["database_error"] = type(exc).__name__
        raise HTTPException(status_code=503, detail="Prediction computed but audit persistence failed") from exc


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

    events: list[dict[str, Any]] = []
    for event_id, event_markets in grouped.items():
        first = event_markets[0]
        api_home = str(first["home_team"])
        api_away = str(first["away_team"])
        home = football_model_name(api_home)
        away = football_model_name(api_away)
        winamax = next((m for m in event_markets if m["bookmaker_key"] == "winamax_fr"), None)
        consensus = consensus_h2h(event_markets, exclude=("winamax_fr",))
        commence_ts = pd.to_datetime(first["commence_time"], utc=True, errors="coerce")
        in_play = bool(not pd.isna(commence_ts) and commence_ts <= pd.Timestamp.now(tz="UTC"))
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
            "consensus": consensus,
            "decision": "abstention",
            "reasons": [],
        }
        if in_play:
            base["reasons"].append("match commencé : modèle pré-match désactivé")
            events.append(base)
            continue
        if home not in model_teams or away not in model_teams:
            base["reasons"].append("identité non couverte par le modèle embarqué")
            events.append(base)
            continue
        prediction_date = pd.to_datetime(first["commence_time"], utc=True).date().isoformat()
        prediction = _football_prediction(FootballRequest(home_team=home, away_team=away, date=prediction_date, league=league))
        model_probs = [prediction["probabilities"]["home"], prediction["probabilities"]["draw"], prediction["probabilities"]["away"]]
        base["model"] = prediction
        if winamax is None:
            base["reasons"].append("cotes Winamax absentes du snapshot fournisseur")
            events.append(base)
            continue
        labels = [api_home, "Draw", api_away]
        if any(label not in winamax["odds"] for label in labels):
            base["reasons"].append("marché Winamax incomplet")
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
            "winamax_available": sum(bool(x["winamax_available"]) for x in events),
            "research_candidates": sum(x["decision"] == "candidat recherche" for x in events),
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
    events: list[dict[str, Any]] = []
    for event_id, event_markets in grouped.items():
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
            events.append(base)
            continue
        labels = [api_p1, api_p2]
        if any(label not in winamax["odds"] for label in labels):
            base["reasons"].append("marché Winamax incomplet")
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
            "winamax_available": sum(bool(x["winamax_available"]) for x in events),
            "research_candidates": sum(x["decision"] == "candidat recherche" for x in events),
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
    payload: dict[str, Any] = {
        "sport": "football",
        "fixture": {"home_team": req.home_team, "away_team": req.away_team, "date": date, "league": req.league},
        "probabilities": {"home": pred["home_win"], "draw": pred["draw"], "away": pred["away_win"]},
        "expected_goals": {"home": pred["expected_home_goals"], "away": pred["expected_away_goals"]},
        "top_scores": pred["top_scores"],
        "warning": "Research probability from a small real-data snapshot; not a production or betting guarantee.",
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
    if STARTUP_STATE.get("database_error"):
        issues.append(f"database startup error: {STARTUP_STATE['database_error']}")
    if STARTUP_STATE.get("model_error"):
        issues.append(f"model startup error: {STARTUP_STATE['model_error']}")
    payload = {
        "status": "ready" if not issues else "not_ready",
        "version": app.version,
        "issues": sorted(set(issues)),
        "models": models,
        "database": db,
        "the_odds_api_configured": odds_client().config.configured,
        "auth_required": SETTINGS.auth_required,
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
    }


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
