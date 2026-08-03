from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _evenly_spaced(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    if count >= len(frame):
        return frame.copy()
    if count <= 1:
        return frame.head(1).copy()
    positions = [round(index * (len(frame) - 1) / (count - 1)) for index in range(count)]
    positions = sorted(set(positions))
    cursor = 0
    while len(positions) < count:
        if cursor not in positions:
            positions.append(cursor)
        cursor += 1
    return frame.iloc[sorted(positions[:count])].copy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select a deterministic event sample for a V4 evidence campaign stage.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--candidate-plan", help="Optional V4.2 immutable candidate plan restricting eligible event IDs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.target < 1 or args.target > 1000:
        raise ValueError("--target must be between 1 and 1000")
    frame = pd.read_csv(ROOT / args.input)
    required = {"event_id", "sport_key", "commence_time"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")
    frame = frame.copy()
    frame["commence_time"] = pd.to_datetime(frame["commence_time"], utc=True, errors="raise", format="mixed")
    frame = frame.sort_values(["commence_time", "event_id"], kind="stable").drop_duplicates("event_id")
    if args.candidate_plan:
        candidate = json.loads((ROOT / args.candidate_plan).read_text(encoding="utf-8"))
        candidate_material = dict(candidate)
        candidate_plan_id = str(candidate_material.pop("candidate_plan_id", ""))
        expected_plan_id = "CPL-" + hashlib.sha256(
            json.dumps(candidate_material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:24].upper()
        if not candidate_plan_id or candidate_plan_id != expected_plan_id:
            raise ValueError("candidate plan failed immutable plan integrity validation")
        allowed_ids = sorted(str(value) for value in candidate.get("candidate_event_ids") or [])
        expected_hash = str(candidate.get("candidate_event_ids_sha256") or "")
        actual_hash = hashlib.sha256(
            json.dumps(allowed_ids, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if not allowed_ids or actual_hash != expected_hash:
            raise ValueError("candidate plan event pool is missing or failed integrity validation")
        if int(candidate.get("recommended_selected_events") or 0) != int(args.target):
            raise ValueError("candidate plan recommended event count does not match --target")
        frame = frame[frame["event_id"].astype(str).isin(set(allowed_ids))].copy()
        if len(frame) < int(args.target):
            raise ValueError(
                f"current discovery contains only {len(frame)} of {args.target} immutable candidate events"
            )
    selected = _evenly_spaced(frame, min(args.target, len(frame)))
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output, index=False)
    print(f"Selected {len(selected)} of {len(frame)} discovered events for target {args.target}.")
    if len(selected) < args.target:
        print(f"WARNING: discovery returned fewer than the target stage ({len(selected)}/{args.target}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
