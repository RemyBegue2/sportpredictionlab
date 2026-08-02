from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Découvre les identifiants d'événements historiques The Odds API.")
    p.add_argument("--sport-key", required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD inclus")
    p.add_argument("--snapshot-hour-utc", type=int, default=12)
    p.add_argument("--lookahead-days", type=int, default=7)
    p.add_argument("--max-calls", type=int, default=400)
    p.add_argument("--output", default="data/odds_api/historical/events.csv")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--force-refresh", action="store_true")
    return p.parse_args()


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        raise SystemExit("--end doit être postérieur à --start")
    days = (end - start).days + 1
    if days > args.max_calls:
        print(f"ABORT: {days} appels planifiés > plafond {args.max_calls}")
        return 3
    schedule = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        snapshot = datetime.combine(day, time(args.snapshot_hour_utc), tzinfo=timezone.utc)
        schedule.append({
            "snapshot_at": iso_z(snapshot),
            "commence_time_from": iso_z(datetime.combine(day, time.min, tzinfo=timezone.utc)),
            "commence_time_to": iso_z(datetime.combine(day + timedelta(days=args.lookahead_days), time.max, tzinfo=timezone.utc)),
        })
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / "event_discovery_plan.json").write_text(json.dumps({
        "sport_key": args.sport_key,
        "calls": len(schedule),
        "schedule": schedule,
        "execute": args.execute,
    }, indent=2), encoding="utf-8")
    print(f"{len(schedule)} appels historiques planifiés pour {args.sport_key}")
    if not args.execute:
        print("DRY-RUN terminé. Ajoutez --execute après contrôle du nombre d'appels.")
        return 0

    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    events: dict[str, dict] = {}
    for i, item in enumerate(schedule, 1):
        response = client.historical_events(
            args.sport_key,
            snapshot_at=item["snapshot_at"],
            commence_time_from=item["commence_time_from"],
            commence_time_to=item["commence_time_to"],
            force_refresh=args.force_refresh,
        )
        payload = response.payload.get("data", []) if isinstance(response.payload, dict) else response.payload
        for event in payload or []:
            event_id = str(event.get("id", ""))
            if not event_id:
                continue
            record = events.setdefault(event_id, {
                "sport_key": event.get("sport_key", args.sport_key),
                "event_id": event_id,
                "commence_time": event.get("commence_time"),
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "first_seen_snapshot": response.payload.get("timestamp", item["snapshot_at"]) if isinstance(response.payload, dict) else item["snapshot_at"],
                "last_seen_snapshot": item["snapshot_at"],
            })
            record["last_seen_snapshot"] = item["snapshot_at"]
        print(f"{i}/{len(schedule)} · événements uniques={len(events)} · quota restant={response.quota.remaining}")
    frame = pd.DataFrame(events.values())
    if not frame.empty:
        frame = frame.sort_values(["commence_time", "event_id"])
    frame.to_csv(output, index=False)
    print(f"Écrit: {output} ({len(frame)} événements)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
