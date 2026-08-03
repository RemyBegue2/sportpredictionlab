from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "development",
            "APP_AUTH_REQUIRED": "false",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'entrypoint.db'}",
        }
    )
    return env


def test_db_migrate_direct_script(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/db_migrate.py"],
        cwd=ROOT,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "'status': 'ok'" in result.stdout


def test_db_migrate_module(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.db_migrate"],
        cwd=ROOT,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "'status': 'ok'" in result.stdout


def test_odds_sync_entrypoints_import() -> None:
    for command in (
        [sys.executable, "scripts/sync_current_odds.py", "--help"],
        [sys.executable, "-m", "scripts.sync_current_odds", "--help"],
    ):
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "Persist current pre-match odds" in result.stdout


def test_db_migrate_cloud_requires_postgres_and_secrets(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "RAILWAY_ENVIRONMENT": "production",
            "RAILWAY_SERVICE_ID": "railway-runtime-test",
            "APP_ENV": "production",
            "APP_AUTH_REQUIRED": "true",
            "APP_COOKIE_SECURE": "true",
            "APP_DATABASE_PATH": str(tmp_path / "must-not-be-used.db"),
        }
    )
    env.pop("DATABASE_URL", None)
    env.pop("APP_PASSWORD", None)
    env.pop("APP_SESSION_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.db_migrate"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "DATABASE_URL must reference a PostgreSQL service" in result.stdout
    assert "APP_PASSWORD is missing" in result.stdout
    assert "APP_SESSION_SECRET must contain at least 32 characters" in result.stdout


def test_db_migrate_ignores_remote_target_environment_in_ci(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env["RAILWAY_ENVIRONMENT"] = "production"
    env.pop("RAILWAY_SERVICE_ID", None)
    env.pop("RAILWAY_ENVIRONMENT_ID", None)

    result = subprocess.run(
        [sys.executable, "-m", "scripts.db_migrate"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "'status': 'ok'" in result.stdout


def test_db_migrate_direct_script_from_foreign_workdir(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/db_migrate.py")],
        cwd=tmp_path,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "'status': 'ok'" in result.stdout


def test_docker_runtime_installs_package_and_sets_pythonpath() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "PYTHONPATH=/app" in dockerfile
    assert "sports_prediction_lab.pth" in dockerfile
    assert "from sports_predictor.cloud_config import CloudSettings" in dockerfile


def test_railway_predeploy_uses_absolute_runtime_context() -> None:
    config = (ROOT / "railway.toml").read_text(encoding="utf-8")
    assert "cd /app" in config
    assert "PYTHONPATH=/app" in config
    assert "python -m scripts.db_migrate" in config


def test_v32_worker_and_cloud_cycle_configs() -> None:
    cron = (ROOT / "railway.cron.toml").read_text(encoding="utf-8")
    worker = (ROOT / "railway.worker.toml").read_text(encoding="utf-8")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "scripts.sync_daily_predictions" in cron
    assert "0 */6 * * *" in cron
    assert "scripts.run_historical_backfill" in worker
    assert "BACKFILL_MAX_CREDITS" in worker
    assert "scripts.sync_daily_predictions" in render
    assert "DAILY_ODDS_ENABLED" in render


def test_v32_historical_scripts_have_safe_dry_run_help() -> None:
    for module in (
        "scripts.plan_historical_backfill",
        "scripts.run_historical_backfill",
        "scripts.prepare_market_benchmark",
        "scripts.run_market_benchmark",
        "scripts.sync_recent_results",
    ):
        result = subprocess.run([sys.executable, "-m", module, "--help"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr


def test_railway_deployments_use_detached_mode_and_never_ci_log_streaming() -> None:
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    deploy_workflows = []
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        if "railway up" not in text:
            continue
        deploy_workflows.append(workflow.name)
        assert "railway up --ci" not in text, f"{workflow.name} still uses fragile Railway CI log streaming"
        for line in text.splitlines():
            if "railway up" in line:
                assert "--detach" in line, f"{workflow.name} must queue Railway deployments in detached mode"
    assert deploy_workflows == [
        "deploy-production.yml",
        "rebuild-fresh-football.yml",
        "recompute-latest-evidence.yml",
        "rollback-production.yml",
        "run-evidence-campaign.yml",
        "run-historical-sample.yml",
    ]


def test_web_deploy_workflows_keep_exact_public_release_verification() -> None:
    for name in (
        "deploy-production.yml",
        "rebuild-fresh-football.yml",
        "recompute-latest-evidence.yml",
        "rollback-production.yml",
        "run-evidence-campaign.yml",
        "run-historical-sample.yml",
    ):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "scripts.post_deploy_verify" in text, f"{name} must verify the queued web deployment"
        assert "--expected-commit" in text, f"{name} must verify the exact deployed commit"
