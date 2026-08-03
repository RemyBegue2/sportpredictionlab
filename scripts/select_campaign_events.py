from __future__ import annotations

import argparse
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
