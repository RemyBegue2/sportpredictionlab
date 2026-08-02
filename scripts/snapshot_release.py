from __future__ import annotations

import argparse
import json
from pathlib import Path

from sports_predictor.release_registry import snapshot_model_release

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot the current model release before a promotion or rollback.")
    parser.add_argument("--release-id")
    args = parser.parse_args()
    result = snapshot_model_release(ROOT, release_id=args.release_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
