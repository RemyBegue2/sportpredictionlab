from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the readable V3.9 event and bookmaker coverage tables.")
    parser.add_argument("--report", default="artifacts/evidence_report_v3_9.json")
    parser.add_argument("--events-output", default="artifacts/event_outcomes_v3_9.csv")
    parser.add_argument("--bookmakers-output", default="artifacts/bookmaker_coverage_v3_9.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    events_path = Path(args.events_output)
    bookmakers_path = Path(args.bookmakers_output)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    bookmakers_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(report.get("event_outcomes") or []).to_csv(events_path, index=False)
    pd.DataFrame(report.get("bookmaker_coverage") or []).to_csv(bookmakers_path, index=False)
    print(
        json.dumps(
            {
                "event_rows": len(report.get("event_outcomes") or []),
                "bookmaker_rows": len(report.get("bookmaker_coverage") or []),
                "events_output": str(events_path),
                "bookmakers_output": str(bookmakers_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
