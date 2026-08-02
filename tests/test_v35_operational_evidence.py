from __future__ import annotations

from pathlib import Path
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, MetaData, select

from sports_predictor.artifacts import write_artifact_manifest
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import (
    dispose_database,
    init_database,
    list_models,
    list_releases,
    model_status_history,
    register_model,
    register_release,
    set_model_status,
    shadow_summary,
)
from sports_predictor.release_registry import (
    APP_VERSION,
    build_release_evidence,
    rollback_model_release,
    snapshot_model_release,
    verify_release_manifest,
    write_release_manifest,
)
from scripts.export_handoff import build_handoff
from scripts.portable_db_backup import backup, restore


def _settings(path: Path) -> CloudSettings:
    return CloudSettings(
        environment="test",
        auth_required=False,
        app_password=None,
        session_secret="test-session-secret-that-is-long-enough",
        cookie_secure=False,
        database_url=f"sqlite:///{path}",
        odds_sync_sports=("soccer_epl",),
        odds_stale_minutes=15,
        model_version=APP_VERSION,
    )


def _release_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    (root / "static").mkdir()
    (root / "sports_predictor").mkdir()
    (root / "webapp.py").write_text("APP='test'\n", encoding="utf-8")
    (root / "static" / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "static" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (root / "sports_predictor" / "release_registry.py").write_text("APP_VERSION='test'\n", encoding="utf-8")
    (artifacts / "football_model.joblib").write_bytes(b"football-v1")
    (artifacts / "tennis_model.joblib").write_bytes(b"tennis-v1")
    (artifacts / "metrics.json").write_text(json.dumps({"football": {"log_loss": 1.0}}), encoding="utf-8")
    (artifacts / "fresh_rebuild_report.json").write_text(json.dumps({
        "version": "3.5.0",
        "promoted": True,
        "dataset": {"sha256": "dataset-hash", "rows": 1900, "cutoff": "2026-05-24"},
        "model": {"trained_until": "2026-05-24"},
    }), encoding="utf-8")
    write_artifact_manifest(
        [artifacts / "football_model.joblib", artifacts / "tennis_model.joblib", artifacts / "metrics.json"],
        artifacts / "artifact_manifest.json",
    )
    return root


def test_release_manifest_is_verifiable_and_secret_free(tmp_path: Path, monkeypatch) -> None:
    root = _release_root(tmp_path)
    monkeypatch.setenv("APP_PASSWORD", "must-not-appear")
    monkeypatch.setenv("THE_ODDS_API_KEY", "must-not-appear-either")
    payload = write_release_manifest(root, version=APP_VERSION)
    verified = verify_release_manifest(root)
    serialized = json.dumps(payload)
    assert payload["app"]["version"] == APP_VERSION
    assert payload["integrity"]["artifact_integrity_ok"] is True
    assert payload["football_model"]["artifact_sha256"]
    assert verified["release_id"] == payload["release_id"]
    assert "must-not-appear" not in serialized
    assert payload["safety"]["secrets_exported"] is False


def test_release_snapshot_and_rollback_are_hash_verified(tmp_path: Path) -> None:
    root = _release_root(tmp_path)
    snapshot = snapshot_model_release(root, release_id="known-good")
    model = root / "artifacts" / "football_model.joblib"
    model.write_bytes(b"broken-model")
    dry = rollback_model_release(root, release_id="known-good", dry_run=True)
    assert dry["status"] == "dry_run"
    result = rollback_model_release(root, release_id="known-good", dry_run=False)
    assert result["status"] == "rolled_back"
    assert model.read_bytes() == b"football-v1"
    assert snapshot["release_id"] == "known-good"


def test_model_lifecycle_is_explicit_and_single_active(tmp_path: Path) -> None:
    import webapp

    dispose_database()
    try:
        init_database(_settings(tmp_path / "registry.db"))
        register_model(
            model_id="football-a", sport="football", version="1", status="candidate",
            trained_until="2026-05-01", dataset_hash="a", metrics={"log_loss": 1.0},
        )
        register_model(
            model_id="football-b", sport="football", version="2", status="shadow",
            trained_until="2026-06-01", dataset_hash="b", metrics={"log_loss": 0.9},
        )
        set_model_status(model_id="football-a", version="1", new_status="shadow", reason="passed offline checks")
        set_model_status(model_id="football-a", version="1", new_status="active", reason="approved for controlled use")
        set_model_status(model_id="football-b", version="2", new_status="active", reason="new champion")
        by_id = {row["model_id"]: row for row in list_models()}
        assert by_id["football-a"]["status"] == "degraded"
        assert by_id["football-b"]["status"] == "active"
        history = model_status_history(limit=20)
        assert any(row["new_status"] == "active" and row["model_id"] == "football-b" for row in history)
        assert any(row["new_status"] == "degraded" and row["model_id"] == "football-a" for row in history)
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)


def test_release_registry_keeps_current_and_previous(tmp_path: Path) -> None:
    import webapp

    dispose_database()
    try:
        init_database(_settings(tmp_path / "releases.db"))
        first = {"release_id": "r1", "app": {"version": "3.5.0", "source_commit": "aaa", "environment": "test"}}
        second = {"release_id": "r2", "app": {"version": "3.5.1", "source_commit": "bbb", "environment": "test"}}
        register_release(first)
        register_release(second)
        releases = {row["release_id"]: row for row in list_releases()}
        assert releases["r1"]["status"] == "previous"
        assert releases["r2"]["status"] == "running"
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)


def test_system_status_and_public_release_proof() -> None:
    import webapp

    with TestClient(webapp.app) as client:
        proof = client.get("/api/release")
        assert proof.status_code == 200
        assert proof.json()["version"] == APP_VERSION
        assert proof.json()["automatic_bet_placement"] is False
        status = client.get("/api/system/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["release"]["app"]["version"] == APP_VERSION
        assert "deployment_contract" in payload
        assert payload["continuity"]["secrets_exported"] is False
        assert "by_model_horizon" in payload["shadow"]["summary"]


def test_handoff_export_contains_no_secrets(monkeypatch) -> None:
    monkeypatch.setenv("APP_PASSWORD", "do-not-export-this")
    monkeypatch.setenv("THE_ODDS_API_KEY", "do-not-export-this-either")
    payload = build_handoff()
    serialized = json.dumps(payload)
    assert "do-not-export-this" not in serialized
    assert payload["safety"]["secrets_exported"] is False
    assert payload["current_version"] == APP_VERSION



def test_runtime_reregistration_preserves_explicit_model_status(tmp_path: Path) -> None:
    import webapp

    dispose_database()
    try:
        init_database(_settings(tmp_path / "preserve.db"))
        register_model(
            model_id="football-stable", sport="football", version="1", status="active",
            trained_until="2026-05-01", dataset_hash="hash", metrics={"log_loss": 1.0},
        )
        register_model(
            model_id="football-stable", sport="football", version="1", status="degraded",
            trained_until="2026-05-01", dataset_hash="hash", metrics={"log_loss": 0.99},
            update_status=False,
        )
        model = next(row for row in list_models() if row["model_id"] == "football-stable")
        assert model["status"] == "active"
        assert model["metrics"]["log_loss"] == 0.99
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)

def test_portable_database_backup_and_restore_to_empty_target(tmp_path: Path) -> None:
    import webapp

    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    backup_file = tmp_path / "backup.json.gz"
    dispose_database()
    try:
        init_database(_settings(source))
        register_model(
            model_id="football-backup", sport="football", version="1", status="shadow",
            trained_until="2026-05-01", dataset_hash="hash", metrics={"log_loss": 1.0},
        )
        result = backup(f"sqlite:///{source}", backup_file)
        assert result["tables"]["model_registry"] == 1
        dry = restore(f"sqlite:///{target}", backup_file, execute=False)
        assert dry["status"] == "dry_run"
        restored = restore(f"sqlite:///{target}", backup_file, execute=True)
        assert restored["status"] == "restored"
        engine = create_engine(f"sqlite:///{target}", future=True)
        metadata = MetaData()
        metadata.reflect(bind=engine)
        with engine.connect() as connection:
            count = connection.scalar(select(func.count()).select_from(metadata.tables["model_registry"]))
        assert count == 1
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)
