from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from sports_predictor.evidence_acceleration import build_tennis_dataset_package

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalise and audit a zero-credit tennis archive.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--license-status", choices=["unknown", "research_only", "approved"], default="unknown")
    parser.add_argument("--output-dir", default="artifacts/tennis_dataset_import_v4_9")
    parser.add_argument("--supersedes-dataset-id", default=None)
    args = parser.parse_args()

    source_path = Path(args.input)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    package = build_tennis_dataset_package(
        pd.read_csv(source_path),
        source=args.source,
        license_status=args.license_status,
        supersedes_dataset_id=args.supersedes_dataset_id,
    )
    accepted = package.pop("accepted")
    quarantined = package.pop("quarantined")
    accepted.to_csv(output_dir / "accepted.csv", index=False)
    quarantined.to_csv(output_dir / "quarantined.csv", index=False)
    (output_dir / "catalog.json").write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": package["catalog"]["readiness"]["status"],
        "dataset_id": package["catalog"]["dataset_id"],
        "accepted_rows": len(accepted),
        "quarantined_rows": len(quarantined),
        "provider_credits_consumed": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
