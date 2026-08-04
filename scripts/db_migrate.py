from __future__ import annotations

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from sports_predictor.cloud_config import CloudSettings, cloud_runtime_detected
from sports_predictor.database import Base, configure_database, database_engine, database_summary

BASELINE_REVISION = "20260804_0001"
HEAD_REVISION = "20260804_0002"
CORE_TABLE = "events"
NEW_TABLES = {"dataset_catalog", "holdout_generations"}


def _alembic_config(settings: CloudSettings) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def migrate(settings: CloudSettings) -> dict[str, object]:
    configure_database(settings, force=True)
    engine = database_engine()
    before = set(inspect(engine).get_table_names())
    config = _alembic_config(settings)

    if "alembic_version" not in before:
        if CORE_TABLE not in before:
            # One-time bootstrap for a brand-new installation. Future changes are
            # handled only by Alembic revisions.
            Base.metadata.create_all(engine)
            command.stamp(config, "head")
            mode = "bootstrap_and_stamp_head"
        else:
            command.stamp(config, BASELINE_REVISION)
            command.upgrade(config, "head")
            mode = "adopt_existing_and_upgrade"
    else:
        command.upgrade(config, "head")
        mode = "upgrade"

    after = set(inspect(engine).get_table_names())
    missing = sorted(NEW_TABLES - after)
    if missing:
        raise RuntimeError(f"missing migrated tables: {missing}")
    return {
        "mode": mode,
        "revision": HEAD_REVISION,
        "new_tables": sorted(NEW_TABLES),
        "tables_before": len(before),
        "tables_after": len(after),
    }


def main() -> int:
    settings = CloudSettings.from_env(ROOT)
    cloud_detected = cloud_runtime_detected()
    issues = settings.readiness_issues()
    if cloud_detected and settings.database_url.startswith("sqlite"):
        issues.append("DATABASE_URL must reference a PostgreSQL service in cloud deployment")
    if issues:
        print({"status": "error", "issues": sorted(set(issues))})
        return 2
    migration = migrate(settings)
    summary = database_summary()
    print({"status": "ok", "database_connected": summary["connected"], "alembic": migration})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
