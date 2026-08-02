from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.historical_benchmark import prepare_football_market_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare leakage-safe model/Winamax/consensus rows for benchmarking.")
    parser.add_argument("--results-csv", required=True)
    parser.add_argument("--events-csv", required=True)
    parser.add_argument("--odds-csv", required=True)
    parser.add_argument("--stage", default="t-1h")
    parser.add_argument("--initial-train", type=int, default=300)
    parser.add_argument("--horizon", type=int, default=100)
    parser.add_argument("--max-folds", type=int, default=20)
    parser.add_argument("--output-dir", default="data/benchmark")
    args = parser.parse_args()

    results = pd.read_csv(args.results_csv)
    events = pd.read_csv(args.events_csv)
    odds = pd.read_csv(args.odds_csv)
    prepared, mapping, report = prepare_football_market_benchmark(
        results=results,
        provider_events=events,
        odds_rows=odds,
        target_stage=args.stage,
        initial_train=args.initial_train,
        horizon=args.horizon,
        max_folds=args.max_folds,
    )
    output = ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(output / f"evaluation_{args.stage}.csv", index=False)
    mapping.to_csv(output / "event_mapping.csv", index=False)
    payload = report.__dict__
    (output / "preparation_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if len(prepared) else 4


if __name__ == "__main__":
    raise SystemExit(main())
