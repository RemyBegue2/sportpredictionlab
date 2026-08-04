from __future__ import annotations

import argparse
import json
from pathlib import Path

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import (
    init_database,
    record_benchmark_run,
    register_dataset_catalog,
    register_holdout_generation,
)
from sports_predictor.evidence_acceleration import build_evidence_acceleration_report
from sports_predictor.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run zero-credit evidence acceleration for football and tennis.")
    parser.add_argument("--output", default="artifacts/evidence_acceleration_v4_9.json")
    parser.add_argument("--tennis-input", default=None)
    parser.add_argument("--source", default="local_tennis_archive")
    parser.add_argument("--license-status", choices=["unknown", "research_only", "approved"], default="research_only")
    args = parser.parse_args()

    tennis_path = None if not args.tennis_input else Path(args.tennis_input)
    if tennis_path is not None and not tennis_path.is_absolute():
        tennis_path = ROOT / tennis_path
    report = build_evidence_acceleration_report(
        root=ROOT,
        tennis_path=tennis_path,
        source=args.source,
        license_status=args.license_status,
    )
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    catalog = report["tennis"]["catalog"]
    generation = report["tennis"]["holdout_generation"]
    catalog_id = register_dataset_catalog(catalog)
    generation_id = register_holdout_generation(generation)
    run_id = record_benchmark_run(
        sport_key="dual_sport_evidence_acceleration",
        model_version=APP_VERSION,
        status=str(report.get("status") or "collecting"),
        config={
            "mode": "zero_credit_evidence_acceleration",
            "provider_calls": 0,
            "maximum_new_football_challengers": 2,
            "holdout_generations": True,
        },
        report=report,
        summary={
            "football_status": report["football"]["status"],
            "tennis_status": catalog["readiness"]["status"],
            "dataset_id": catalog["dataset_id"],
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
        },
    )
    report["run"] = {"id": run_id, "status": report["status"]}
    report["registry"] = {"dataset_catalog_record_id": catalog_id, "holdout_generation_record_id": generation_id}
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if report["limits"]["provider_credits_consumed"] != 0:
        raise SystemExit("evidence acceleration must consume zero provider credits")
    print(json.dumps({
        "status": report["status"],
        "run_id": run_id,
        "football": report["football"]["status"],
        "tennis": catalog["readiness"]["status"],
        "provider_credits_consumed": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
