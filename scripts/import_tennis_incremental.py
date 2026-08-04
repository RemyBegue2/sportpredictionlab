from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from sports_predictor.controlled_decision import build_incremental_tennis_package

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a new zero-credit tennis archive into a versioned dataset.")
    parser.add_argument("--previous", required=True, help="Previous accepted.csv or equivalent archive")
    parser.add_argument("--incoming", required=True, help="New tennis CSV")
    parser.add_argument("--previous-dataset-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--license-status", choices=["unknown", "research_only", "approved"], default="research_only")
    parser.add_argument("--output-dir", default="artifacts/tennis_incremental_v4_9")
    args = parser.parse_args()

    previous = Path(args.previous)
    incoming = Path(args.incoming)
    output_dir = Path(args.output_dir)
    if not previous.is_absolute():
        previous = ROOT / previous
    if not incoming.is_absolute():
        incoming = ROOT / incoming
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    package = build_incremental_tennis_package(
        pd.read_csv(previous),
        pd.read_csv(incoming),
        source=args.source,
        license_status=args.license_status,
        previous_dataset_id=args.previous_dataset_id,
    )
    accepted = package.pop("accepted")
    quarantined = package.pop("quarantined")
    accepted.to_csv(output_dir / "accepted.csv", index=False)
    quarantined.to_csv(output_dir / "quarantined.csv", index=False)
    (output_dir / "catalog.json").write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": package["catalog"]["readiness"]["status"],
        "dataset_id": package["catalog"]["dataset_id"],
        "supersedes": args.previous_dataset_id,
        "merged_rows": len(accepted),
        "new_rows": package["incremental"]["new_rows"],
        "result_corrections": package["incremental"]["result_corrections"],
        "provider_credits_consumed": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
