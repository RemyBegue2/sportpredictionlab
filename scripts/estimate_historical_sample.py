from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.sample_plan import build_sample_request_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an immutable zero-credit request plan for a controlled historical sample.")
    parser.add_argument("--sport-key", default="soccer_epl")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--sample-events", type=int, default=30)
    parser.add_argument("--horizons", nargs="+", type=float, default=[1.0])
    parser.add_argument("--bookmakers", nargs="+", default=["winamax_fr", "betclic_fr", "unibet_fr", "pmu_fr", "pinnacle"])
    parser.add_argument("--max-discovery-calls", type=int, default=14)
    parser.add_argument("--max-odds-credits", type=int, default=120)
    parser.add_argument("--output", default="artifacts/historical_sample_request.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_sample_request_plan(
        sport_key=args.sport_key,
        start_date=args.start,
        end_date=args.end,
        sample_events=args.sample_events,
        horizons_hours=args.horizons,
        bookmakers=args.bookmakers,
        max_discovery_calls=args.max_discovery_calls,
        max_odds_credits=args.max_odds_credits,
    )
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(plan.to_dict(), indent=2))
    print("ZERO-CREDIT ESTIMATE: no provider request was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
