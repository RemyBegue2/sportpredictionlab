from __future__ import annotations

from pathlib import Path

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import database_summary, init_database


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    summary = database_summary()
    print({"status": "ok", "database_connected": summary["connected"], "tables_initialized": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
