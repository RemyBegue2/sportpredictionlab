from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp import SETTINGS, _daily_slate_payload


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate zero-credit model-only daily football predictions.")
    p.add_argument("--date", help="YYYY-MM-DD; defaults to Europe/Paris today")
    p.add_argument("--horizon-days", type=int, default=None, help="Also prepare upcoming fixtures within this horizon")
    return p


def main() -> int:
    args = parser().parse_args()
    requested = args.date or datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    horizon = SETTINGS.daily_fixture_horizon_days if args.horizon_days is None else args.horizon_days
    payload = _daily_slate_payload(requested, horizon_days=horizon, refresh=True)
    summary = payload.get("summary") or {}
    result = {
        "status": "ok",
        "date": requested,
        "source": payload.get("source"),
        "fixtures_today": summary.get("fixtures_today", 0),
        "model_predictions": summary.get("model_predictions", 0),
        "upcoming_predictions": summary.get("upcoming_predictions", 0),
        "credits_consumed": summary.get("credits_consumed", 0),
        "unsupported_events": len(payload.get("unsupported_events") or []),
        "daily_odds_enabled": SETTINGS.daily_odds_enabled,
        "automatic_bet_placement": False,
    }
    print(json.dumps(result, ensure_ascii=False))
    if payload.get("fixture_status") == "unavailable" and not summary.get("model_predictions"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
