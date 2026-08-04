from __future__ import annotations

import argparse
import json
from pathlib import Path

from sports_predictor.challenger_factory import build_challenger_factory_report
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import init_database, record_benchmark_run
from sports_predictor.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the zero-credit sport challenger factory.")
    parser.add_argument("--output", default="artifacts/challenger_factory_v4_9.json")
    args = parser.parse_args()
    report = build_challenger_factory_report(root=ROOT)
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    run_id = record_benchmark_run(
        sport_key="sport_challenger_factory",
        model_version=APP_VERSION,
        status=str(report.get("status") or "collecting"),
        config={
            "mode": "bounded_sport_challenger_factory",
            "provider_calls": 0,
            "maximum_models_per_sport": ((report.get("limits") or {}).get("maximum_models_per_sport")),
        },
        report=report,
        summary={
            "football_status": ((report.get("sports") or {}).get("football") or {}).get("status"),
            "tennis_status": ((report.get("sports") or {}).get("tennis") or {}).get("status"),
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
        },
    )
    report["run"] = {"id": run_id, "status": report.get("status")}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if int((report.get("limits") or {}).get("provider_credits_consumed", -1)) != 0:
        raise SystemExit("challenger factory must consume zero provider credits")
    print(f"challenger_factory_status={report['status']} run_id={run_id} provider_credits_consumed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
