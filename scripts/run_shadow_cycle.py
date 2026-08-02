from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import (
    due_shadow_events,
    init_database,
    record_shadow_cycle,
    settle_shadow_predictions,
    shadow_cycle_lock,
)
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


def _merge_counts(target: dict[str, int], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            target[key] = target.get(key, 0) + value


def _duration_ms(started_monotonic: float) -> int:
    return max(0, int((time.monotonic() - started_monotonic) * 1000))


def main() -> int:
    args = parser().parse_args()
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    sports = list(args.sports or settings.odds_sync_sports)
    started = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    errors: list[dict[str, str]] = []
    diagnostics: dict[str, int] = {}
    events_seen = 0
    created = 0
    reused = 0
    settled = 0
    quota_remaining: int | None = None

    with shadow_cycle_lock() as lock_acquired:
        if not lock_acquired:
            cycle_id = record_shadow_cycle(
                status="skipped_locked", sports=sports, events_seen=0, predictions_created=0,
                predictions_reused=0, predictions_settled=0, quota_remaining=None,
                errors=[], diagnostics={"lock_contention": 1}, started_at=started,
                duration_ms=_duration_ms(started_monotonic), lock_acquired=False,
            )
            print(json.dumps({"status": "skipped_locked", "cycle_id": cycle_id}))
            return 0

        quota = odds_client().quota_status()
        known_remaining = quota.get("remaining")
        quota_before = int(known_remaining) if known_remaining is not None else None
        if not args.force and quota_before is not None and quota_before <= settings.shadow_quota_floor:
            cycle_id = record_shadow_cycle(
                status="skipped_quota", sports=sports, events_seen=0, predictions_created=0,
                predictions_reused=0, predictions_settled=0, quota_remaining=quota_before,
                errors=[{"type": "quota_guard", "message": "quota is at or below SHADOW_QUOTA_FLOOR"}],
                diagnostics={"quota_guard": 1}, quota_before=quota_before,
                started_at=started, duration_ms=_duration_ms(started_monotonic), lock_acquired=True,
            )
            print(json.dumps({"status": "skipped_quota", "cycle_id": cycle_id, "remaining": quota_before, "floor": settings.shadow_quota_floor}))
            return 0

        for sport_key in sports:
            league = SPORT_LEAGUE_MAP.get(sport_key)
            if league is None:
                errors.append({"sport_key": sport_key, "error": "no_bundled_model_mapping"})
                diagnostics["unsupported_sport"] = diagnostics.get("unsupported_sport", 0) + 1
                continue
            try:
                payload = _football_odds_slate(sport_key, league, force_refresh=True)
                summary = payload.get("summary", {})
                _merge_counts(diagnostics, summary)
                events_seen += int(summary.get("events", 0))
                created += int(summary.get("shadow_created", 0))
                reused += int(summary.get("shadow_reused", 0))
                remaining = (payload.get("quota") or {}).get("remaining")
                if remaining is not None:
                    quota_remaining = int(remaining)
            except Exception as exc:  # durable logs keep only the exception type
                errors.append({"sport_key": sport_key, "error": type(exc).__name__})
                diagnostics["provider_errors"] = diagnostics.get("provider_errors", 0) + 1

        if not args.skip_results:
            try:
                result_summary = _sync_results(sports)
                settled = int(result_summary.get("shadow_settled", 0))
                diagnostics["results_events_seen"] = int(result_summary.get("events_seen", 0))
                diagnostics["results_synced"] = int(result_summary.get("results_upserted", 0))
                remaining = result_summary.get("quota_remaining")
                if remaining is not None:
                    quota_remaining = int(remaining)
            except Exception as exc:
                errors.append({"sport_key": "results", "error": type(exc).__name__})
                diagnostics["result_errors"] = diagnostics.get("result_errors", 0) + 1
        else:
            settled = int(settle_shadow_predictions().get("settled", 0))

        if errors:
            status = "partial" if events_seen or settled else "provider_error"
        else:
            status = "success"
        cycle_id = record_shadow_cycle(
            status=status, sports=sports, events_seen=events_seen, predictions_created=created,
            predictions_reused=reused, predictions_settled=settled, quota_remaining=quota_remaining,
            errors=errors, diagnostics=diagnostics, quota_before=quota_before,
            started_at=started, duration_ms=_duration_ms(started_monotonic), lock_acquired=True,
        )

    output = {
        "status": status, "cycle_id": cycle_id, "sports": sports, "events_seen": events_seen,
        "predictions_created": created, "predictions_reused": reused,
        "predictions_settled": settled, "quota_before": quota_before,
        "quota_remaining": quota_remaining, "diagnostics": diagnostics, "errors": errors,
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0 if status in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
