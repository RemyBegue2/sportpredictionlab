from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig
from sports_predictor.sample_plan import select_discovery_dates


EVENT_COLUMNS = [
    "sport_key",
    "event_id",
    "commence_time",
    "home_team",
    "away_team",
    "first_seen_snapshot",
    "last_seen_snapshot",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Découvre les identifiants d'événements historiques The Odds API.")
    p.add_argument("--sport-key", required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD inclus")
    p.add_argument("--snapshot-hour-utc", type=int, default=12)
    p.add_argument("--lookahead-days", type=int, default=7)
    p.add_argument("--max-calls", type=int, default=14)
    p.add_argument("--max-credits", type=int, default=120)
    p.add_argument("--output", default="data/odds_api/historical/events.csv")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--force-refresh", action="store_true")
    return p.parse_args()


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def event_in_window(event: dict[str, Any], *, start_at: str, end_at: str) -> bool:
    raw = event.get("commence_time")
    if not raw:
        return False
    try:
        commence = pd.to_datetime(raw, utc=True, errors="raise", format="mixed")
        lower = pd.to_datetime(start_at, utc=True, errors="raise", format="mixed")
        upper = pd.to_datetime(end_at, utc=True, errors="raise", format="mixed")
    except (TypeError, ValueError):
        return False
    return bool(lower <= commence <= upper)


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start)
    requested_end = date.fromisoformat(args.end)
    if requested_end < start:
        raise SystemExit("--end doit être postérieur à --start")
    if not 0 <= int(args.snapshot_hour_utc) <= 23:
        raise SystemExit("--snapshot-hour-utc doit être compris entre 0 et 23")
    if int(args.lookahead_days) < 1:
        raise SystemExit("--lookahead-days doit être positif")
    if int(args.max_credits) < 0:
        raise SystemExit("--max-credits doit être positif ou nul")

    now = datetime.now(timezone.utc)
    latest_safe_snapshot = now - timedelta(minutes=10)
    effective_end = min(requested_end, latest_safe_snapshot.date())
    if effective_end < start:
        raise SystemExit("La période demandée ne contient encore aucun snapshot historique disponible")

    discovery_days = select_discovery_dates(start, effective_end, int(args.max_calls))
    requested_range_days = (requested_end - start).days + 1
    effective_range_days = (effective_end - start).days + 1
    strategy = "all_days" if len(discovery_days) == effective_range_days else "evenly_spaced"

    schedule: list[dict[str, str]] = []
    seen_snapshots: set[str] = set()
    for day in discovery_days:
        snapshot = datetime.combine(day, time(args.snapshot_hour_utc), tzinfo=timezone.utc)
        if snapshot > latest_safe_snapshot:
            snapshot = latest_safe_snapshot
        snapshot_at = iso_z(snapshot)
        if snapshot_at in seen_snapshots:
            continue
        seen_snapshots.add(snapshot_at)

        window_start = datetime.combine(max(day, start), time.min, tzinfo=timezone.utc)
        window_end_day = min(day + timedelta(days=int(args.lookahead_days)), requested_end)
        window_end = datetime.combine(window_end_day, time.max, tzinfo=timezone.utc)
        schedule.append(
            {
                "snapshot_at": snapshot_at,
                "commence_time_from": iso_z(window_start),
                "commence_time_to": iso_z(window_end),
            }
        )

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    plan_path = output.parent / "event_discovery_plan.json"
    state_path = output.parent / "event_discovery_state.json"
    plan_path.write_text(
        json.dumps(
            {
                "sport_key": args.sport_key,
                "requested_start_date": start.isoformat(),
                "requested_end_date": requested_end.isoformat(),
                "effective_end_date": effective_end.isoformat(),
                "requested_range_days": requested_range_days,
                "effective_range_days": effective_range_days,
                "max_calls": int(args.max_calls),
                "max_credits": int(args.max_credits),
                "strategy": strategy,
                "calls": len(schedule),
                "schedule": schedule,
                "provider_parameters": ["date"],
                "local_event_filtering": True,
                "execute": args.execute,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"{len(schedule)} appels historiques planifiés pour {args.sport_key} "
        f"sur {requested_range_days} jours (stratégie={strategy})"
    )
    if requested_end != effective_end:
        print(f"Fin future ramenée au dernier jour historique disponible: {effective_end}")
    if not args.execute:
        print("DRY-RUN terminé. Ajoutez --execute après contrôle du nombre d'appels.")
        return 0

    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    events: dict[str, dict[str, Any]] = {}
    consumed_credits = 0
    completed_calls = 0
    for i, item in enumerate(schedule, 1):
        response = client.historical_events(
            args.sport_key,
            snapshot_at=item["snapshot_at"],
            force_refresh=args.force_refresh,
        )
        actual_cost = 0 if response.from_cache else int(response.quota.last_cost or 0)
        if actual_cost < 0:
            raise RuntimeError("Le fournisseur a renvoyé un coût de quota négatif")
        if consumed_credits + actual_cost > int(args.max_credits):
            raise RuntimeError(
                f"Le plafond global de {args.max_credits} crédits serait dépassé pendant la découverte"
            )
        consumed_credits += actual_cost
        completed_calls += 1

        payload = response.payload.get("data", []) if isinstance(response.payload, dict) else response.payload
        for event in payload or []:
            if not isinstance(event, dict):
                continue
            if not event_in_window(
                event,
                start_at=item["commence_time_from"],
                end_at=item["commence_time_to"],
            ):
                continue
            event_id = str(event.get("id", "")).strip()
            if not event_id:
                continue
            record = events.setdefault(
                event_id,
                {
                    "sport_key": event.get("sport_key", args.sport_key),
                    "event_id": event_id,
                    "commence_time": event.get("commence_time"),
                    "home_team": event.get("home_team"),
                    "away_team": event.get("away_team"),
                    "first_seen_snapshot": (
                        response.payload.get("timestamp", item["snapshot_at"])
                        if isinstance(response.payload, dict)
                        else item["snapshot_at"]
                    ),
                    "last_seen_snapshot": item["snapshot_at"],
                },
            )
            record["last_seen_snapshot"] = item["snapshot_at"]
        print(
            f"{i}/{len(schedule)} · événements uniques={len(events)} · "
            f"coût découverte={consumed_credits} · quota restant={response.quota.remaining}"
        )

    frame = pd.DataFrame(events.values(), columns=EVENT_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["commence_time", "event_id"], kind="stable")
    frame.to_csv(output, index=False)
    state = {
        "status": "completed" if len(frame) else "no_events",
        "completed_calls": completed_calls,
        "planned_calls": len(schedule),
        "consumed_credits": consumed_credits,
        "remaining_credit_cap": max(0, int(args.max_credits) - consumed_credits),
        "event_count": int(len(frame)),
        "output": str(output.relative_to(ROOT)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Écrit: {output} ({len(frame)} événements)")
    print(json.dumps(state, indent=2))
    if frame.empty:
        print(
            "Aucun événement n'a été découvert. Vérifiez la période, la couverture historique "
            "du sport et l'accès de l'abonnement au endpoint historique."
        )
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
