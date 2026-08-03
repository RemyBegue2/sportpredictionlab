from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.evidence_campaign import build_campaign_plan, load_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a zero-credit V4.1 evidence campaign plan.")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--target-stage", type=int, required=True)
    parser.add_argument("--max-credits", type=int, required=True)
    parser.add_argument("--baseline", choices=("consensus", "winamax"), default="consensus")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date")
    parser.add_argument("--previous-evidence", default="artifacts/evidence_report_v3_9.json")
    parser.add_argument("--output", default="artifacts/evidence_campaign_plan_v4.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    previous = load_json(ROOT / args.previous_evidence)
    output = ROOT / args.output
    previous_campaign = load_json(output)
    start_date = args.start_date
    end_date = args.end_date
    if (
        args.mode == "continue_current_stage"
        and previous_campaign
        and int(previous_campaign.get("target_stage") or 0) == int(args.target_stage)
        and str(previous_campaign.get("baseline") or "") == str(args.baseline)
        and int(previous_campaign.get("max_credits") or -1) == int(args.max_credits)
    ):
        start_date = str(previous_campaign.get("start_date") or start_date)
        end_date = str(previous_campaign.get("end_date") or end_date or "") or None
    plan = build_campaign_plan(
        mode=args.mode,
        target_stage=args.target_stage,
        max_credits=args.max_credits,
        baseline=args.baseline,
        previous_evidence=previous,
        current_campaign=previous_campaign,
        start_date=start_date,
        end_date=end_date,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(plan.to_dict(), indent=2))
    print("ZERO-CREDIT CAMPAIGN PLAN: no provider request was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
