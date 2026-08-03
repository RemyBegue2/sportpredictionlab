from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from sports_predictor.cloud_auth import AuthenticationGateMiddleware, establish_session
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import (
    database_summary,
    dispose_database,
    init_database,
    persist_odds_rows,
    recent_predictions,
    record_prediction,
)


ROOT = Path(__file__).resolve().parents[1]


def _settings(database_url: str, *, auth_required: bool = False) -> CloudSettings:
    return CloudSettings(
        environment="test",
        auth_required=auth_required,
        app_password="a-very-long-test-password" if auth_required else None,
        session_secret="s" * 48,
        cookie_secure=False,
        database_url=database_url,
        odds_sync_sports=("soccer_epl",),
        odds_stale_minutes=15,
        model_version="3.1.0-test",
    )


def test_cloud_settings_reject_insecure_production():
    settings = CloudSettings(
        environment="production",
        auth_required=True,
        app_password="short",
        session_secret="short",
        cookie_secure=False,
        database_url="sqlite:////tmp/test.db",
        odds_sync_sports=("soccer_epl",),
        odds_stale_minutes=15,
        model_version="3.1.0",
    )
    issues = settings.readiness_issues()
    assert any("APP_PASSWORD" in x for x in issues)
    assert any("APP_SESSION_SECRET" in x for x in issues)
    assert any("PostgreSQL" in x for x in issues)
    assert any("COOKIE" in x for x in issues)


def test_authentication_and_csrf_gate():
    settings = _settings("sqlite:///:memory:", auth_required=True)
    app = FastAPI()
    app.add_middleware(AuthenticationGateMiddleware, settings=settings)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, https_only=False, same_site="strict")

    @app.post("/api/auth/login")
    def login(request: Request):
        return {"csrf": establish_session(request)}

    @app.get("/api/private")
    def private():
        return {"ok": True}

    @app.get("/api/ready")
    def ready():
        return {"ok": True}

    @app.post("/api/write")
    def write():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/api/private").status_code == 401
    assert client.get("/api/ready").status_code == 200
    login_response = client.post("/api/auth/login")
    assert login_response.status_code == 200
    csrf = login_response.json()["csrf"]
    assert client.get("/api/private").status_code == 200
    assert client.post("/api/write").status_code == 403
    assert client.post("/api/write", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_database_persists_snapshots_and_predictions(tmp_path):
    import webapp

    test_settings = _settings(f"sqlite:///{tmp_path / 'cloud.db'}")
    dispose_database()
    try:
        init_database(test_settings)
        rows = pd.DataFrame([{
            "event_id": "event-1",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-10T19:00:00Z",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "bookmaker_key": "winamax_fr",
            "bookmaker_title": "Winamax",
            "bookmaker_last_update": "2026-08-10T12:00:00Z",
            "market_key": "h2h",
            "market_last_update": "2026-08-10T12:01:00Z",
            "outcome_name": "Arsenal",
            "price": 2.05,
            "point": None,
            "snapshot_time": "2026-08-10T12:02:00Z",
        }])
        first = persist_odds_rows(rows, fetched_at="2026-08-10T12:03:00Z", sport_key="soccer_epl")
        second = persist_odds_rows(rows, fetched_at="2026-08-10T12:04:00Z", sport_key="soccer_epl")
        assert first["inserted_snapshots"] == 1
        assert second["inserted_snapshots"] == 0
        prediction_id = record_prediction(
            sport="football",
            model_version="3.1.0-test",
            fixture={"home_team": "Arsenal", "away_team": "Chelsea"},
            probabilities={"home": 0.5, "draw": 0.25, "away": 0.25},
            market_analysis=None,
            decision="abstention",
        )
        assert prediction_id > 0
        summary = database_summary()
        assert summary["events"] == 1
        assert summary["odds_snapshots"] == 1
        assert summary["predictions"] == 1
        assert recent_predictions(1)[0]["model_version"] == "3.1.0-test"
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)


def test_cloud_deployment_configs_are_safe_and_parseable():
    render = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    assert {service["type"] for service in render["services"]} == {"web", "cron"}
    web = next(service for service in render["services"] if service["type"] == "web")
    assert web["healthCheckPath"] == "/api/ready"
    env = {item["key"]: item for item in web["envVars"]}
    assert env["APP_SESSION_SECRET"]["generateValue"] is True
    assert env["APP_PASSWORD"]["sync"] is False
    assert env["THE_ODDS_API_KEY"]["sync"] is False
    assert render["databases"][0]["plan"] == "basic-256mb"

    railway = (ROOT / "railway.toml").read_text(encoding="utf-8")
    cron = (ROOT / "railway.cron.toml").read_text(encoding="utf-8")
    assert 'healthcheckPath = "/api/ready"' in railway
    assert "python -m scripts.db_migrate" in railway
    assert 'cronSchedule = "*/15 * * * *"' in cron
    assert "python -m scripts.run_shadow_cycle" in cron
    assert "THE_ODDS_API_KEY=" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")
