from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
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
from sports_predictor.version import APP_VERSION


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
    p.add_argument("--max-cost-per-call", type=int, default=1)
    p.add_argument("--output", default="data/odds_api/historical/events.csv")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--force-refresh", action="store_true")
    p.add_argument(
        "--retry-uncertain",
        action="store_true",
        help="Autorise explicitement le rejeu d'un appel dont l'issue fournisseur est inconnue.",
    )
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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _events_from_existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists() or not path.stat().st_size:
        return {}
    frame = pd.read_csv(path)
    if frame.empty or "event_id" not in frame.columns:
        return {}
    return {
        str(row["event_id"]): {column: row.get(column) for column in EVENT_COLUMNS}
        for row in frame.to_dict(orient="records")
        if str(row.get("event_id") or "").strip()
    }


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
    if int(args.max_cost_per_call) < 1:
        raise SystemExit("--max-cost-per-call doit être au moins égal à 1")

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

    plan_material = {
        "schema_version": "2.0",
        "app_version": APP_VERSION,
        "sport_key": args.sport_key,
        "requested_start_date": start.isoformat(),
        "requested_end_date": requested_end.isoformat(),
        "effective_end_date": effective_end.isoformat(),
        "snapshot_hour_utc": int(args.snapshot_hour_utc),
        "lookahead_days": int(args.lookahead_days),
        "max_calls": int(args.max_calls),
        "max_credits": int(args.max_credits),
        "max_cost_per_call": int(args.max_cost_per_call),
        "schedule": schedule,
    }
    plan_id = "DSP-" + hashlib.sha256(_canonical_json(plan_material).encode("utf-8")).hexdigest()[:24].upper()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    plan_path = output.parent / "event_discovery_plan.json"
    state_path = output.parent / "event_discovery_state.json"
    plan = {
        **plan_material,
        "plan_id": plan_id,
        "requested_range_days": requested_range_days,
        "effective_range_days": effective_range_days,
        "strategy": strategy,
        "calls": len(schedule),
        "provider_parameters": ["date"],
        "local_event_filtering": True,
        "execute": args.execute,
    }
    _atomic_json(plan_path, plan)

    print(
        f"{len(schedule)} appels historiques planifiés pour {args.sport_key} "
        f"sur {requested_range_days} jours (stratégie={strategy}, plan={plan_id})"
    )
    if requested_end != effective_end:
        print(f"Fin future ramenée au dernier jour historique disponible: {effective_end}")
    if not args.execute:
        print("DRY-RUN terminé. Ajoutez --execute après contrôle du nombre d'appels.")
        return 0

    existing_state: dict[str, Any] = {}
    if state_path.exists():
        existing_state = json.loads(state_path.read_text(encoding="utf-8"))
        if existing_state.get("plan_id") != plan_id:
            raise RuntimeError("Le checkpoint de découverte appartient à un autre plan immuable")
    uncertain = {int(value) for value in existing_state.get("uncertain_calls", [])}
    if uncertain and not args.retry_uncertain:
        raise RuntimeError(
            "Des appels de découverte ont une issue fournisseur incertaine; relancez avec --retry-uncertain après vérification du quota"
        )

    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    events = _events_from_existing(output)
    completed_numbers = {int(value) for value in existing_state.get("completed_call_numbers", [])}
    consumed_credits = int(existing_state.get("consumed_credits") or 0)
    ledger = list(existing_state.get("credit_ledger") or [])
    state: dict[str, Any] = {
        "schema_version": "2.0",
        "app_version": APP_VERSION,
        "plan_id": plan_id,
        "status": "running",
        "completed_call_numbers": sorted(completed_numbers),
        "completed_calls": len(completed_numbers),
        "planned_calls": len(schedule),
        "consumed_credits": consumed_credits,
        "remaining_credit_cap": max(0, int(args.max_credits) - consumed_credits),
        "event_count": len(events),
        "credit_ledger": ledger,
        "uncertain_calls": sorted(uncertain),
        "output": str(output.relative_to(ROOT)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_json(state_path, state)

    for number, item in enumerate(schedule, 1):
        if number in completed_numbers:
            continue
        if consumed_credits + int(args.max_cost_per_call) > int(args.max_credits):
            raise RuntimeError("Le plafond de crédits ne permet pas de réserver le prochain appel de découverte")

        state.update(
            {
                "status": "running",
                "in_flight_call": number,
                "reserved_credit_upper_bound": int(args.max_cost_per_call),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _atomic_json(state_path, state)
        try:
            response = client.historical_events(
                args.sport_key,
                snapshot_at=item["snapshot_at"],
                force_refresh=args.force_refresh,
            )
        except Exception:
            uncertain.add(number)
            state.update(
                {
                    "status": "interrupted",
                    "uncertain_calls": sorted(uncertain),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _atomic_json(state_path, state)
            raise

        actual_cost = 0 if response.from_cache else int(
            response.quota.last_cost if response.quota.last_cost is not None else int(args.max_cost_per_call)
        )
        if actual_cost < 0:
            raise RuntimeError("Le fournisseur a renvoyé un coût de quota négatif")
        consumed_credits += actual_cost
        if consumed_credits > int(args.max_credits):
            state.update(
                {
                    "status": "credit_cap_exceeded",
                    "consumed_credits": consumed_credits,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _atomic_json(state_path, state)
            raise RuntimeError("Le coût déclaré par le fournisseur a dépassé le plafond réservé")

        payload = response.payload.get("data", []) if isinstance(response.payload, dict) else response.payload
        for event in payload or []:
            if not isinstance(event, dict):
                continue
            if not event_in_window(event, start_at=item["commence_time_from"], end_at=item["commence_time_to"]):
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

        completed_numbers.add(number)
        uncertain.discard(number)
        ledger.append(
            {
                "call_number": number,
                "snapshot_at": item["snapshot_at"],
                "actual_cost": actual_cost,
                "from_cache": bool(response.from_cache),
                "quota_remaining": response.quota.remaining,
                "request_fingerprint": response.request_fingerprint,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        frame = pd.DataFrame(events.values(), columns=EVENT_COLUMNS)
        if not frame.empty:
            frame = frame.sort_values(["commence_time", "event_id"], kind="stable")
        _atomic_csv(output, frame)
        state.update(
            {
                "status": "running",
                "completed_call_numbers": sorted(completed_numbers),
                "completed_calls": len(completed_numbers),
                "consumed_credits": consumed_credits,
                "remaining_credit_cap": max(0, int(args.max_credits) - consumed_credits),
                "event_count": len(frame),
                "credit_ledger": ledger,
                "uncertain_calls": sorted(uncertain),
                "in_flight_call": None,
                "reserved_credit_upper_bound": 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _atomic_json(state_path, state)
        print(
            f"{len(completed_numbers)}/{len(schedule)} · événements uniques={len(events)} · "
            f"coût découverte={consumed_credits} · quota restant={response.quota.remaining}"
        )

    frame = pd.DataFrame(events.values(), columns=EVENT_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["commence_time", "event_id"], kind="stable")
    _atomic_csv(output, frame)
    state.update(
        {
            "status": "completed" if len(frame) else "no_events",
            "completed_call_numbers": sorted(completed_numbers),
            "completed_calls": len(completed_numbers),
            "consumed_credits": consumed_credits,
            "remaining_credit_cap": max(0, int(args.max_credits) - consumed_credits),
            "event_count": int(len(frame)),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "in_flight_call": None,
            "reserved_credit_upper_bound": 0,
        }
    )
    _atomic_json(state_path, state)
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
