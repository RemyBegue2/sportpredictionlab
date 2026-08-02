from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import init_database, settle_shadow_predictions, shadow_summary


def main() -> int:
    init_database(CloudSettings.from_env(ROOT))
    result = settle_shadow_predictions()
    print(json.dumps({"status": "ok", **result, "summary": shadow_summary(sport_key="soccer_epl")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
