from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from scripts.portable_db_backup import normalize_database_url
from sports_predictor.cloud_auth import AuthenticationGateMiddleware
from sports_predictor.cloud_config import CloudSettings


def _settings() -> CloudSettings:
    return CloudSettings(
        environment="production",
        auth_required=True,
        app_password="a-very-long-test-password",
        session_secret="s" * 48,
        cookie_secure=True,
        database_url="postgresql+psycopg://user:password@example.com:5432/railway",
        odds_sync_sports=("soccer_epl",),
        odds_stale_minutes=15,
        model_version="4.2.1-test",
    )


def test_ready_is_public_but_private_api_remains_protected() -> None:
    settings = _settings()
    app = FastAPI()
    app.add_middleware(AuthenticationGateMiddleware, settings=settings)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, https_only=False, same_site="strict")

    @app.get("/api/ready")
    def ready():
        return {"status": "ready"}

    @app.get("/api/private")
    def private():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/api/ready").status_code == 200
    assert client.get("/api/private").status_code == 401


def test_backup_url_normalization_strips_quotes_and_upgrades_driver() -> None:
    normalized = normalize_database_url("  'postgresql://user:password@example.com:5432/railway'  ")
    assert normalized == "postgresql+psycopg://user:password@example.com:5432/railway"


def test_backup_url_rejects_empty_port_without_leaking_credentials() -> None:
    with pytest.raises(RuntimeError) as caught:
        normalize_database_url("postgresql://secret-user:secret-pass@example.com:/railway")
    message = str(caught.value)
    assert "invalid or empty port" in message
    assert "secret-user" not in message
    assert "secret-pass" not in message


def test_backup_url_rejects_railway_private_host_in_github(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(RuntimeError, match="cannot reach a Railway private hostname"):
        normalize_database_url("postgresql://user:password@postgres.railway.internal:5432/railway")


def test_backup_cli_reports_actionable_error_without_traceback(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://secret-user:secret-pass@example.com:/railway"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.portable_db_backup", "--backup", "--file", str(tmp_path / "backup.json.gz")],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "invalid or empty port" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert "secret-user" not in result.stdout + result.stderr
    assert "secret-pass" not in result.stdout + result.stderr


def test_startup_errors_are_logged_without_exception_details(monkeypatch, caplog) -> None:
    import logging
    import webapp

    def fail_database(_settings):
        raise RuntimeError("postgresql://secret-user:secret-pass@host:5432/railway")

    def fail_models():
        raise ValueError("private model path")

    previous_state = dict(webapp.STARTUP_STATE)
    try:
        monkeypatch.setattr(webapp, "init_database", fail_database)
        monkeypatch.setattr(webapp, "resources", fail_models)
        with caplog.at_level(logging.INFO, logger="sports_prediction_lab.startup"):
            webapp.initialize_runtime()

        assert "database startup failed error_type=RuntimeError" in caplog.text
        assert "model startup failed error_type=ValueError" in caplog.text
        assert "startup readiness version=4.2.1" in caplog.text
        assert "secret-user" not in caplog.text
        assert "secret-pass" not in caplog.text
        assert "private model path" not in caplog.text
    finally:
        webapp.STARTUP_STATE.clear()
        webapp.STARTUP_STATE.update(previous_state)


def test_readiness_recovers_from_stale_startup_errors() -> None:
    import webapp
    from fastapi.testclient import TestClient

    previous_state = dict(webapp.STARTUP_STATE)
    try:
        webapp.STARTUP_STATE.update({"database_error": "RuntimeError", "model_error": "ValueError"})
        response = TestClient(webapp.app).get("/api/ready")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ready"
        assert webapp.STARTUP_STATE == {"database_error": None, "model_error": None}
    finally:
        webapp.STARTUP_STATE.clear()
        webapp.STARTUP_STATE.update(previous_state)
