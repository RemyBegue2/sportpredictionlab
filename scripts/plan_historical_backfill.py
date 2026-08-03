from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.backfill_control import VALIDATION_EVENT_LIMIT, build_plan_identity
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import create_backfill_job, init_database
from sports_predictor.odds_backtest import HistoricalPlan, build_historical_plan

DEFAULT_BOOKMAKERS = ["winamax_fr", "betclic_fr", "unibet_fr", "pmu_fr", "pinnacle"]


def _evenly_spaced_sample(events: pd.DataFrame, sample_size: int) -> pd.DataFrame:
    """Select a deterministic sample covering the whole available period."""
    if sample_size >= len(events):
        return events.copy()
    if sample_size <= 1:
        return events.head(1).copy()
    positions = [round(i * (len(events) - 1) / (sample_size - 1)) for i in range(sample_size)]
    positions = sorted(set(positions))
    if len(positions) < sample_size:
        for position in range(len(events)):
            if position not in positions:
                positions.append(position)
                if len(positions) == sample_size:
                    break
        positions.sort()
    return events.iloc[positions[:sample_size]].copy()


def build_budget_capped_validation_plan(
    events: pd.DataFrame,
    *,
    requested_events: int,
    max_credits: int,
    horizons: Sequence[float],
    closing_minutes: int,
    include_closing: bool,
    markets: Sequence[str],
    bookmakers: Sequence[str],
) -> tuple[pd.DataFrame, HistoricalPlan]:
    """Select the largest deterministic sample that fits the immutable cap."""
    upper = min(max(1, int(requested_events)), len(events), VALIDATION_EVENT_LIMIT)
    last_plan: HistoricalPlan | None = None
    last_sample: pd.DataFrame | None = None
    for count in range(upper, 0, -1):
        sample = _evenly_spaced_sample(events, count)
        plan = build_historical_plan(
            sample,
            horizons_hours=horizons,
            closing_minutes=closing_minutes,
            include_closing=include_closing,
            markets=markets,
            bookmakers=bookmakers,
        )
        last_sample, last_plan = sample, plan
        if plan.estimated_credits <= int(max_credits):
            return sample, plan
    assert last_sample is not None and last_plan is not None
    return last_sample, last_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an immutable, auditable, budget-capped historical odds backfill plan.")
    parser.add_argument("--events-csv", required=True)
    parser.add_argument("--horizons", nargs="+", type=float, default=[24, 6, 1])
    parser.add_argument("--closing-minutes", type=int, default=10)
    parser.add_argument("--closing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--markets", nargs="+", default=["h2h"])
    parser.add_argument("--bookmakers", nargs="+", default=DEFAULT_BOOKMAKERS)
    parser.add_argument("--max-credits", type=int, required=True)
    parser.add_argument("--sample-events", type=int, default=VALIDATION_EVENT_LIMIT)
    parser.add_argument("--full", action="store_true", help="Plan every event; full execution will require exact plan approval.")
    parser.add_argument("--output-dir", default="data/odds_api/backfill")
    parser.add_argument("--register-job", action="store_true")
    parser.add_argument("--plan-request-json", help="Optional zero-credit request plan to link to this immutable provider plan.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if int(args.max_credits) < 1:
        raise ValueError("--max-credits must be positive after discovery costs are deducted")
    events = pd.read_csv(args.events_csv)
    required = {"sport_key", "event_id", "commence_time"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")
    events = events.copy()
    events["commence_time"] = pd.to_datetime(events["commence_time"], utc=True, errors="raise", format="mixed")
    events = events.sort_values(["commence_time", "event_id"], kind="stable").drop_duplicates("event_id")
    available_events = len(events)
    if available_events == 0:
        raise ValueError("No historical events were discovered; no provider odds plan can be created")

    requested_event_count = available_events if args.full else max(1, min(int(args.sample_events), VALIDATION_EVENT_LIMIT))
    if args.full:
        selected_events = events
        plan = build_historical_plan(
            selected_events,
            horizons_hours=args.horizons,
            closing_minutes=args.closing_minutes,
            include_closing=bool(args.closing),
            markets=args.markets,
            bookmakers=args.bookmakers,
        )
    else:
        selected_events, plan = build_budget_capped_validation_plan(
            events,
            requested_events=requested_event_count,
            max_credits=int(args.max_credits),
            horizons=args.horizons,
            closing_minutes=int(args.closing_minutes),
            include_closing=bool(args.closing),
            markets=args.markets,
            bookmakers=args.bookmakers,
        )

    output = ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    plan.requests.to_csv(output / "requests.csv", index=False)
    plan.targets.to_csv(output / "targets.csv", index=False)
    selected_count = int(selected_events["event_id"].nunique())
    summary = {
        "version": "3.8.3",
        "sport_keys": sorted(plan.requests["sport_key"].astype(str).unique().tolist()),
        "available_event_count": int(available_events),
        "requested_event_count": int(requested_event_count),
        "event_count": selected_count,
        "budget_limited": bool(not args.full and selected_count < min(requested_event_count, available_events)),
        "execution_mode": "full" if args.full else "validation",
        "validation_event_limit": VALIDATION_EVENT_LIMIT,
        "event_sampling_strategy": "all_events" if args.full or selected_count == available_events else "evenly_spaced_budget_capped",
        "request_count": int(len(plan.requests)),
        "target_count": int(len(plan.targets)),
        "estimated_credits": int(plan.estimated_credits),
        "max_credits": int(args.max_credits),
        "markets": list(plan.markets),
        "bookmakers": list(plan.bookmakers),
        "include_closing": bool(args.closing),
        "safe_to_execute": bool(plan.estimated_credits <= args.max_credits),
        "full_execution_requires_exact_plan_approval": bool(args.full),
    }
    if args.plan_request_json:
        request_plan_path = ROOT / args.plan_request_json
        request_plan = json.loads(request_plan_path.read_text(encoding="utf-8"))
        summary["plan_request_id"] = request_plan.get("plan_request_id")
        summary["plan_request_sha256"] = __import__("hashlib").sha256(request_plan_path.read_bytes()).hexdigest()
    summary.update(build_plan_identity(summary, plan.requests, plan.targets))
    if args.register_job:
        settings = CloudSettings.from_env(ROOT)
        init_database(settings)
        summary["database_job_id"] = create_backfill_job(
            sport_key=summary["sport_keys"][0] if len(summary["sport_keys"]) == 1 else "multi",
            plan=summary,
            request_count=len(plan.requests),
            estimated_credits=plan.estimated_credits,
        )
    (output / "plan.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["safe_to_execute"]:
        print(
            "ABORT: even one event exceeds the remaining credit cap. "
            "Increase max_odds_credits or use fewer bookmakers/horizons."
        )
        return 3
    if summary["budget_limited"]:
        print(
            f"BUDGET ADAPTATION: requested {requested_event_count} events, "
            f"selected {selected_count} within {args.max_credits} credits."
        )
    if args.full:
        print(f"FULL PLAN prepared. Execution requires --approve-plan {summary['plan_id']}")
    else:
        print("VALIDATION PLAN prepared within the immutable remaining credit cap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
