from __future__ import annotations

import argparse
import json
from pathlib import Path

from sports_predictor.release_registry import rollback_model_release

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify or restore a prior model release snapshot.")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--execute", action="store_true", help="Actually restore files. Default is dry-run.")
    args = parser.parse_args()
    result = rollback_model_release(ROOT, release_id=args.release_id, dry_run=not args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
