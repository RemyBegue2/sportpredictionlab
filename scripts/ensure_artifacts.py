from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.artifacts import verify_artifact_manifest


def main() -> int:
    artifacts = ROOT / "artifacts"
    manifest = artifacts / "artifact_manifest.json"
    required = [artifacts / "football_model.joblib", artifacts / "tennis_model.joblib", artifacts / "metrics.json"]
    try:
        if manifest.exists() and all(path.exists() for path in required):
            verify_artifact_manifest(artifacts, manifest)
            print("Verified prebuilt model artifacts")
            return 0
    except Exception:
        pass
    return subprocess.call([sys.executable, "-m", "scripts.train_snapshot"], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
