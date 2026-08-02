from __future__ import annotations

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import database_summary, init_database



def main() -> int:
    settings = CloudSettings.from_env(ROOT)
    cloud_detected = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER"))
    issues = settings.readiness_issues()
    if cloud_detected and settings.database_url.startswith("sqlite"):
        issues.append("DATABASE_URL must reference a PostgreSQL service in cloud deployment")
    if issues:
        print({"status": "error", "issues": sorted(set(issues))})
        return 2
    init_database(settings)
    summary = database_summary()
    print({"status": "ok", "database_connected": summary["connected"], "tables_initialized": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
