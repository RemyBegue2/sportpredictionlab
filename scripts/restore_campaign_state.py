from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore a compatible V4.1 campaign checkpoint extracted from a GitHub artifact.")
    parser.add_argument("--current-plan", default="artifacts/evidence_campaign_plan_v4.json")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--destination-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    current_path = ROOT / args.current_plan
    artifact_root = Path(args.artifact_root).resolve()
    destination = (ROOT / args.destination_root).resolve()
    previous_path = artifact_root / "artifacts" / "evidence_campaign_plan_v4.json"
    source_campaign = artifact_root / "data" / "odds_api" / "campaign"
    discovery_state_path = source_campaign / "event_discovery_state.json"
    if not previous_path.exists() or not discovery_state_path.exists() or not source_campaign.exists():
        print(json.dumps({"restored": False, "reason": "artifact_has_no_discovery_checkpoint"}))
        return 3

    current = _load(current_path)
    previous = _load(previous_path)
    keys = ("app_version", "campaign_key", "target_stage", "baseline", "max_credits", "start_date", "end_date")
    mismatches = {
        key: {"current": current.get(key), "previous": previous.get(key)}
        for key in keys
        if current.get(key) != previous.get(key)
    }
    current_commit = str(current.get("source_commit") or "unknown")
    previous_commit = str(previous.get("source_commit") or "unknown")
    if current_commit != "unknown" and previous_commit != "unknown" and current_commit != previous_commit:
        mismatches["source_commit"] = {"current": current_commit, "previous": previous_commit}
    if mismatches:
        print(json.dumps({"restored": False, "reason": "checkpoint_plan_mismatch", "mismatches": mismatches}, indent=2))
        return 3

    target_campaign = destination / "data" / "odds_api" / "campaign"
    if target_campaign.exists():
        shutil.rmtree(target_campaign)
    target_campaign.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_campaign, target_campaign)

    source_benchmark = artifact_root / "data" / "benchmark"
    target_benchmark = destination / "data" / "benchmark"
    if source_benchmark.exists():
        if target_benchmark.exists():
            shutil.rmtree(target_benchmark)
        shutil.copytree(source_benchmark, target_benchmark)

    discovery_state = _load(target_campaign / "event_discovery_state.json")
    discovery_status = str(discovery_state.get("status") or "in_progress")
    discovery_complete = discovery_status in {"completed", "no_events"}
    backfill_plan_path = target_campaign / "backfill" / "plan.json"
    backfill_state_path = target_campaign / "backfill" / "state.json"
    backfill_ready = backfill_plan_path.exists() and backfill_state_path.exists()
    backfill_state = _load(backfill_state_path) if backfill_ready else {}

    print(
        json.dumps(
            {
                "restored": True,
                "reason": "compatible_checkpoint_restored",
                "discovery_status": discovery_status,
                "discovery_complete": discovery_complete,
                "discovery_completed_calls": len(discovery_state.get("completed_call_numbers") or []),
                "discovery_credits": int(discovery_state.get("consumed_credits") or 0),
                "backfill_ready": backfill_ready,
                "backfill_status": str(backfill_state.get("status") or "not_planned"),
                "completed_requests": len(backfill_state.get("completed") or []),
                "snapshot_credits": int(backfill_state.get("consumed_credits") or 0),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
