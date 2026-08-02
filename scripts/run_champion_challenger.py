from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.champion_challenger import (
    DecisionPolicy,
    build_model_decision,
    run_champion_challenger,
)
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.market_benchmark import BenchmarkPolicy
from sports_predictor.database import (
    init_database,
    record_benchmark_run,
    record_model_decision,
    shadow_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run leakage-safe champion–challenger evidence evaluation.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--contenders", nargs="+", default=["model", "blend50"])
    parser.add_argument("--champion", default="model")
    parser.add_argument("--champion-model-key")
    parser.add_argument("--sport-key", default="soccer_epl")
    parser.add_argument("--output", default="artifacts/champion_challenger_v3_6.json")
    parser.add_argument("--minimum-train", type=int, default=150)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--bootstrap-samples", type=int, default=1500)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    frame = pd.read_csv(args.input)
    benchmark_policy = BenchmarkPolicy(
        minimum_predictions=500,
        exploratory_predictions=200,
        minimum_train=args.minimum_train,
        n_folds=args.folds,
        bootstrap_samples=args.bootstrap_samples,
    )
    report = run_champion_challenger(
        frame,
        contenders=args.contenders,
        benchmark_policy=benchmark_policy,
    )
    settings = CloudSettings.from_env(ROOT)
    shadow = None
    run_id = None
    if args.persist:
        init_database(settings)
        shadow = shadow_summary(sport_key=args.sport_key)
    decision = build_model_decision(
        report,
        shadow_summary=shadow,
        champion=args.champion,
        champion_model_key=args.champion_model_key,
        policy=DecisionPolicy(),
    )
    payload = {"benchmark": report, "decision": decision}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.persist:
        run_id = record_benchmark_run(
            sport_key=args.sport_key,
            model_version=settings.model_version,
            status="completed" if decision["status"] != "not_evaluable" else "not_evaluable",
            config={
                "contenders": args.contenders,
                "champion": args.champion,
                "benchmark_policy": benchmark_policy.__dict__,
            },
            report=report,
            summary={
                "status": decision["status"],
                "reason": decision["reason"],
                "evaluated_rows": decision.get("historical_predictions", 0),
            },
        )
        record_model_decision(
            sport_key=args.sport_key,
            champion=args.champion,
            decision=decision,
            benchmark_run_id=run_id,
        )
    print(json.dumps({"output": str(output.relative_to(ROOT)), "benchmark_run_id": run_id, "decision": decision}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
