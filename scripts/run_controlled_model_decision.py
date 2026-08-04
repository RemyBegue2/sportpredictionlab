from __future__ import annotations

import argparse
import json
from pathlib import Path

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.controlled_decision import build_controlled_model_decision_report
from sports_predictor.database import init_database, record_benchmark_run, register_holdout_generation
from sports_predictor.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the zero-credit controlled model decision round.")
    parser.add_argument("--output", default="artifacts/controlled_model_decision_v4_9.json")
    args = parser.parse_args()

    report = build_controlled_model_decision_report(root=ROOT, app_version=APP_VERSION)
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    football = report["football"]
    consulted_id = register_holdout_generation(football["consulted_holdout_generation"])
    promotion_id = register_holdout_generation(football["promotion_holdout_generation"])
    run_id = record_benchmark_run(
        sport_key="controlled_model_decision",
        model_version=APP_VERSION,
        status=str(report.get("status") or "collecting"),
        config={
            "mode": "bounded_controlled_model_decision",
            "provider_calls": 0,
            "maximum_football_challengers": 2,
            "promotion_holdout_required": True,
        },
        report=report,
        summary={
            "football_status": football.get("status"),
            "tennis_status": report["tennis"]["training_status"],
            "production_validation": report["production_validation"]["status"],
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
        },
    )
    report["run"] = {"id": run_id, "status": report["status"]}
    report["registry"] = {
        "consulted_holdout_record_id": consulted_id,
        "promotion_holdout_record_id": promotion_id,
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if report["limits"]["provider_credits_consumed"] != 0:
        raise SystemExit("controlled model decision must consume zero provider credits")
    print(json.dumps({
        "status": report["status"],
        "decision_id": report["decision_id"],
        "football": football["status"],
        "tennis": report["tennis"]["training_status"],
        "production": report["production_validation"]["status"],
        "provider_credits_consumed": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
