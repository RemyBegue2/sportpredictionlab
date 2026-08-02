from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import due_shadow_events, init_database, record_shadow_cycle, settle_shadow_predictions
from webapp import SPORT_LEAGUE_MAP, _football_odds_slate, odds_client


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one finite shadow-mode cycle and exit.")
    p.add_argument("--sports", nargs="+", default=None, help="The Odds API sport keys. Defaults to ODDS_SYNC_SPORTS.")
    p.add_argument("--skip-results", action="store_true", help="Skip recent score synchronization.")
    p.add_argument("--force", action="store_true", help="Ignore the configured quota floor.")
    return p


def _sync_results(sports: list[str]) -> dict[str, Any]:
    from scripts.sync_recent_results import sync_results

    due = due_shadow_events()
    event_ids_by_sport: dict[str, list[str]] = {sport: [] for sport in sports}
    for item in due:
        event_ids_by_sport.setdefault(item["sport_key"], []).append(item["provider_event_id"])
    return sync_results(sports=sports, days_from=None, event_ids_by_sport=event_ids_by_sport)


def main() -> int:
    args = parser().parse_args()
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    sports = list(args.sports or settings.odds_sync_sports)
    started = datetime.now(timezone.utc)
    errors: list[dict[str, str]] = []
    events_seen = 0
    created = 0
    reused = 0
    settled = 0
    quota_remaining: int | None = None

    quota = odds_client().quota_status()
    known_remaining = quota.get("remaining")
    if not args.force and known_remaining is not None and int(known_remaining) <= settings.shadow_quota_floor:
        record_shadow_cycle(
            status="quota_guard", sports=sports, events_seen=0, predictions_created=0,
            predictions_reused=0, predictions_settled=0, quota_remaining=int(known_remaining),
            errors=[{"type": "quota_guard", "message": "quota is at or below SHADOW_QUOTA_FLOOR"}],
            started_at=started,
        )
        print(json.dumps({"status": "quota_guard", "remaining": known_remaining, "floor": settings.shadow_quota_floor}))
        return 0

    for sport_key in sports:
        league = SPORT_LEAGUE_MAP.get(sport_key)
        if league is None:
            errors.append({"sport_key": sport_key, "error": "no bundled model mapping"})
            continue
        try:
            payload = _football_odds_slate(sport_key, league, force_refresh=True)
            summary = payload.get("summary", {})
            events_seen += int(summary.get("events", 0))
            created += int(summary.get("shadow_created", 0))
            reused += int(summary.get("shadow_reused", 0))
            remaining = (payload.get("quota") or {}).get("remaining")
            if remaining is not None:
                quota_remaining = int(remaining)
        except Exception as exc:  # sanitized type only in durable cycle log
            errors.append({"sport_key": sport_key, "error": type(exc).__name__})

    if not args.skip_results:
        try:
            result_summary = _sync_results(sports)
            settled = int(result_summary.get("shadow_settled", 0))
            remaining = result_summary.get("quota_remaining")
            if remaining is not None:
                quota_remaining = int(remaining)
        except Exception as exc:
            errors.append({"sport_key": "results", "error": type(exc).__name__})
    else:
        settled = int(settle_shadow_predictions().get("settled", 0))

    status = "ok" if not errors else ("partial_failure" if events_seen or settled else "failed")
    cycle_id = record_shadow_cycle(
        status=status, sports=sports, events_seen=events_seen, predictions_created=created,
        predictions_reused=reused, predictions_settled=settled, quota_remaining=quota_remaining,
        errors=errors, started_at=started,
    )
    output = {
        "status": status, "cycle_id": cycle_id, "sports": sports, "events_seen": events_seen,
        "predictions_created": created, "predictions_reused": reused,
        "predictions_settled": settled, "quota_remaining": quota_remaining, "errors": errors,
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0 if status in {"ok", "partial_failure"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
