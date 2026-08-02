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
