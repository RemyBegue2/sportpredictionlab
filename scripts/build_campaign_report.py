from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.evidence_campaign import evaluate_scale_gate, evidence_stage, load_json, next_stage
from sports_predictor.version import APP_VERSION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the V4.1 canonical campaign decision report from saved evidence.")
    parser.add_argument("--plan", default="artifacts/evidence_campaign_plan_v4.json")
    parser.add_argument("--evidence", default="artifacts/evidence_report_v3_9.json")
    parser.add_argument("--output", default="artifacts/evidence_campaign_v4.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = load_json(ROOT / args.plan) or {}
    evidence = load_json(ROOT / args.evidence) or {}
    baseline = str(plan.get("baseline") or evidence.get("baseline") or "consensus")
    gate = evaluate_scale_gate(evidence, baseline=baseline)
    completed_stage = evidence_stage(evidence, baseline=baseline)
    following_stage = next_stage(completed_stage)
    credits = evidence.get("credits") or {}
    decision = (
        "eligible_for_next_stage_review"
        if gate.get("status") == "PASS" and following_stage is not None
        else "campaign_complete_review_only"
        if gate.get("status") == "PASS" and following_stage is None
        else "stop_and_fix_integrity"
        if gate.get("status") == "FAIL"
        else "hold_and_fix_data_quality"
    )
    report = {
        "schema_version": "2.0",
        "app_version": APP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": plan.get("campaign_id"),
        "campaign_key": plan.get("campaign_key"),
        "source_commit": plan.get("source_commit"),
        "mode": plan.get("mode"),
        "target_stage": plan.get("target_stage"),
        "baseline": baseline,
        "budget": {
            "maximum_credits": plan.get("max_credits", 0),
            "estimated_snapshot_cost": plan.get("estimated_snapshot_cost"),
            "estimated_snapshot_capacity": plan.get("estimated_snapshot_capacity"),
            "discovery_credits": credits.get("discovery_credits", 0),
            "snapshot_credits": credits.get("snapshot_credits", 0),
            "observed_total_credits": credits.get("total_credits", evidence.get("consumed_credits", 0)),
            "remaining_credits": credits.get("remaining_credits"),
        },
        "completed_stage": completed_stage,
        "next_stage": following_stage,
        "scale_gate": gate,
        "decision_gate": evidence.get("decision_gate") or evidence.get("quality_gate") or {"status": "HOLD", "accepted": False},
        "quality_gate": evidence.get("quality_gate") or {"status": "HOLD", "accepted": False},
        "funnel": evidence.get("funnel") or {},
        "rates": evidence.get("rates") or {},
        "benchmark": evidence.get("benchmark") or {},
        "decision": decision,
        "automatic_model_promotion": False,
        "profitability_claim": False,
        "stake_recommendation": False,
        "automatic_bet_placement": False,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
