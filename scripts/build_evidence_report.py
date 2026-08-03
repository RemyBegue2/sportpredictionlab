from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.evidence_quality import build_evidence_quality_report, load_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the V3.9 coverage-funnel and evidence report.")
    parser.add_argument("--plan-dir", default="data/odds_api/backfill")
    parser.add_argument("--events-csv", default="data/odds_api/historical/events.csv")
    parser.add_argument("--discovery-state-json", default="data/odds_api/historical/event_discovery_state.json")
    parser.add_argument("--matches-csv")
    parser.add_argument("--benchmark-json")
    parser.add_argument("--output", default="artifacts/evidence_report_v3_9.json")
    return parser.parse_args()


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() and path.stat().st_size else pd.DataFrame()


def main() -> int:
    args = parse_args()
    plan_dir = ROOT / args.plan_dir
    report = build_evidence_quality_report(
        plan=load_json(plan_dir / "plan.json"),
        state=load_json(plan_dir / "state.json"),
        odds_rows=_read_csv(plan_dir / "historical_odds_long.csv"),
        events=_read_csv(ROOT / args.events_csv),
        matches=_read_csv(ROOT / args.matches_csv) if args.matches_csv else None,
        benchmark=load_json(ROOT / args.benchmark_json) if args.benchmark_json else None,
        requests=_read_csv(plan_dir / "requests.csv"),
        targets=_read_csv(plan_dir / "targets.csv"),
        discovery_state=load_json(ROOT / args.discovery_state_json),
        event_selection=_read_csv(plan_dir / "event_selection.csv"),
    )
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # Data-quality blocks are evidence, not infrastructure failures.  The
    # workflow publishes the report and exposes the verdict in the UI.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
