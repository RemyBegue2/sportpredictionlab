from __future__ import annotations

import argparse
from pathlib import Path

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import init_database, recent_shadow_predictions, record_benchmark_run
from sports_predictor.feature_lab import build_feature_lab_report
from sports_predictor.version import APP_VERSION
from sports_predictor.common import write_json


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the zero-credit calibration and feature laboratory.")
    parser.add_argument("--output", default="artifacts/feature_lab_v4_6.json")
    args = parser.parse_args()
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    rows = recent_shadow_predictions(10000, status="settled")
    report = build_feature_lab_report(rows)
    run_id = record_benchmark_run(
        sport_key="dual_sport_feature_lab",
        model_version=APP_VERSION,
        status="completed" if report["status"] == "ready" else "collecting",
        config={"provider_calls": 0, "mode": "bounded_calibration_feature_lab"},
        report=report,
        summary={
            "overall_reliability": report["overall_reliability"],
            "provider_credits_consumed": 0,
        },
    )
    report["run"] = {"id": run_id}
    write_json(ROOT / args.output, report)
    print(f"feature_lab_status={report['status']} run_id={run_id} provider_credits_consumed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
