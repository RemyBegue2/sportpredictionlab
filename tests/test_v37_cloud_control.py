from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import zipfile

from fastapi.testclient import TestClient

from scripts.build_handoff_bundle import build_bundle
from sports_predictor.control_center import WORKFLOW_CATALOG, build_control_center
from sports_predictor.release_registry import APP_VERSION, build_release_evidence


def _release(*, valid: bool = True) -> dict:
    return {
        "app": {"version": APP_VERSION, "source_commit": "a" * 40, "source_commit_short": "a" * 12},
        "integrity": {"artifact_integrity_ok": valid},
    }


def test_control_center_turns_cloud_state_into_actions() -> None:
    now = datetime(2026, 8, 2, 20, tzinfo=timezone.utc)
    payload = build_control_center(
        release=_release(),
        database={"connected": True, "odds_snapshots": 12, "open_data_quality_issues": 0},
        models=[{"sport": "football", "model_id": "football-1n2-shadow", "version": "fresh", "status": "shadow"}],
        shadow_cycle={"status": "ok", "finished_at": (now - timedelta(hours=3)).isoformat()},
        benchmark={"evaluated_rows": 0},
        model_decision={"decision": {"status": "not_evaluable", "historical_predictions": 0}},
        backfills=[],
        daily_product={"shadow_enabled": True, "historical_evidence_enabled": True},
        now=now,
    )
    assert payload["local_python_required"] is False
    assert payload["operation_mode"] == "github_actions_and_railway"
    assert payload["overall_status"] == "attention"
    assert any(item["workflow"] == "estimate-historical-sample" for item in payload["next_actions"])
    assert {item["id"] for item in payload["workflows"]} >= {
        "deploy-production", "verify-production", "generate-handoff", "backup-database"
    }



def test_control_center_treats_credit_freeze_as_healthy_state() -> None:
    payload = build_control_center(
        release=_release(),
        database={"connected": True, "odds_snapshots": 0, "open_data_quality_issues": 0},
        models=[{"sport": "football", "model_id": "football-1n2-shadow", "version": "fresh", "status": "shadow"}],
        shadow_cycle=None, benchmark={}, model_decision={}, backfills=[],
        daily_product={
            "model_status": "operational_research",
            "prediction_count": 0,
            "fixture_status": "no_fixtures",
            "shadow_enabled": False,
            "historical_evidence_enabled": False,
        },
    )
    checks = {item["id"]: item for item in payload["checks"]}
    assert checks["shadow-cron"]["status"] == "ok"
    assert checks["historical-backfill"]["status"] == "ok"
    assert checks["historical-backfill"]["workflow"] is None


def test_control_center_blocks_unproven_release_and_database() -> None:
    payload = build_control_center(
        release={"app": {"version": APP_VERSION, "source_commit": "unknown"}, "integrity": {"artifact_integrity_ok": False}},
        database={"connected": False},
        models=[],
        shadow_cycle=None,
        benchmark={},
        model_decision={},
        backfills=[],
    )
    assert payload["overall_status"] == "blocked"
    blocked = {item["id"] for item in payload["checks"] if item["status"] == "blocked"}
    assert {"production-release", "database", "model-registry"} <= blocked


def test_workflow_catalog_is_cloud_only_and_guarded() -> None:
    workflows = {item["id"]: item for item in WORKFLOW_CATALOG}
    assert workflows["run-historical-sample"]["confirmation"] == "EXECUTE_SAMPLE"
    assert workflows["rollback-production"]["confirmation"] == "ROLLBACK"
    assert workflows["generate-handoff"]["required_configuration"] == []


def test_packaged_release_manifest_is_runtime_commit_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SOURCE_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "release_manifest.json").write_text(json.dumps({
        "app": {"source_commit": "b" * 40},
    }), encoding="utf-8")
    evidence = build_release_evidence(tmp_path, version=APP_VERSION)
    assert evidence["app"]["source_commit"] == "b" * 40


def test_handoff_bundle_is_secret_free_and_directly_attachable(tmp_path: Path) -> None:
    target = tmp_path / "handoff.zip"
    result = build_bundle(target)
    assert result["secrets_exported"] is False
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        assert "BUNDLE_MANIFEST.json" in names
        assert "handoff/HANDOFF_CURRENT.json" in names
        manifest = json.loads(archive.read("BUNDLE_MANIFEST.json"))
        assert manifest["local_python_required"] is False
        combined = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in names if name.endswith((".json", ".md", ".txt"))
        ).casefold()
        assert "the_odds_api_key=" not in combined
        assert "database_url=" not in combined
        assert "railway_token=" not in combined


def test_all_cloud_workflows_are_manual_and_write_readable_summaries() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = {
        "deploy-production.yml", "verify-production.yml", "generate-handoff.yml",
        "estimate-historical-sample.yml", "run-historical-sample.yml", "historical-validation.yml", "backup-database.yml", "rollback-production.yml",
        "rebuild-fresh-football.yml",
    }
    found = {path.name for path in (root / ".github" / "workflows").glob("*.yml")}
    assert expected <= found
    for name in expected:
        text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "workflow_dispatch:" in text
        assert "GITHUB_STEP_SUMMARY" in text
    historical = (root / ".github" / "workflows" / "run-historical-sample.yml").read_text(encoding="utf-8")
    assert "EXECUTE_SAMPLE" in historical
    assert "scripts.estimate_historical_sample" in historical


def test_control_center_endpoint_and_frontend_contract() -> None:
    import webapp

    with TestClient(webapp.app) as client:
        response = client.get("/api/control-center")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["local_python_required"] is False
    assert payload["safety"]["automatic_bet_placement"] is False

    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "app.js").read_text(encoding="utf-8")
    for element_id in ("controlOverall", "controlChecks", "controlWorkflows", "controlNextActions", "refreshControl"):
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js
    assert "app.js?v=4.3.0" in html


def test_public_release_proof_contains_deployment_safety_contract() -> None:
    import webapp

    with TestClient(webapp.app) as client:
        response = client.get("/api/release")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["version"] == "4.3.0"
    assert payload["automatic_model_promotion"] is False
    assert payload["profitability_claim"] is False
    assert payload["automatic_bet_placement"] is False


def test_cloud_workflow_caps_and_rollback_are_operational() -> None:
    root = Path(__file__).resolve().parents[1]
    workflows = root / ".github" / "workflows"
    historical = (workflows / "run-historical-sample.yml").read_text(encoding="utf-8")
    assert "EXECUTE_SAMPLE" in historical
    assert "--max-odds-credits" in historical

    rollback = (workflows / "rollback-production.yml").read_text(encoding="utf-8")
    assert "source_commit" in rollback
    assert 'git checkout "$SOURCE"' in rollback
    assert "data/real/football_active.csv" in rollback
    assert "release_snapshots/" not in rollback

    deployment = (workflows / "deploy-production.yml").read_text(encoding="utf-8")
    assert "APP_PASSWORD" in deployment
    assert "the post" not in deployment.casefold() or "playwright" in deployment
    assert "scripts.browser_smoke_test" in deployment


def test_browser_smoke_waits_for_control_center_render() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "browser_smoke_test.py").read_text(encoding="utf-8")
    frontend = (root / "static" / "app.js").read_text(encoding="utf-8")

    assert "page.wait_for_function" in script
    assert "value !== '—'" in script
    assert "const controlTask=refreshControl();" in frontend
    assert "control:jsonFetch('/api/control-center')" not in frontend
