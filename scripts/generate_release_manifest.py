from __future__ import annotations

import argparse
import json
from pathlib import Path

from sports_predictor.release_registry import APP_VERSION, write_release_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a secret-free release evidence manifest.")
    parser.add_argument("--output", default="artifacts/release_manifest.json")
    parser.add_argument("--version", default=APP_VERSION)
    args = parser.parse_args()
    target = ROOT / args.output
    payload = write_release_manifest(ROOT, target, version=args.version)
    print(json.dumps({
        "status": "ok",
        "output": str(target.relative_to(ROOT)),
        "release_id": payload["release_id"],
        "version": payload["app"]["version"],
        "source_commit": payload["app"]["source_commit"],
        "artifact_integrity_ok": payload["integrity"]["artifact_integrity_ok"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
