from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import init_database, record_benchmark_run
from sports_predictor.market_benchmark import BenchmarkPolicy, benchmark_summary, run_market_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real historical model-vs-market benchmark.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--sport-key", default="soccer_epl")
    parser.add_argument("--minimum-predictions", type=int, default=500)
    parser.add_argument("--exploratory-predictions", type=int, default=200)
    parser.add_argument("--minimum-train", type=int, default=150)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--output", default="artifacts/market_benchmark_v3_2.json")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    frame = pd.read_csv(args.input)
    policy = BenchmarkPolicy(
        minimum_predictions=args.minimum_predictions,
        exploratory_predictions=args.exploratory_predictions,
        minimum_train=args.minimum_train,
        n_folds=args.folds,
    )
    report = run_market_benchmark(frame, policy=policy)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary = benchmark_summary(report)
    if args.persist:
        settings = CloudSettings.from_env(ROOT)
        init_database(settings)
        record_benchmark_run(
            sport_key=args.sport_key,
            model_version=settings.model_version,
            status="completed" if summary["status"] != "not_evaluable" else "not_evaluable",
            config=policy.__dict__,
            report=report,
            summary=summary,
        )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
