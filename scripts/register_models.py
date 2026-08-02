from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.artifacts import verify_artifact_manifest
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import init_database, list_models, register_model


def main() -> int:
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    manifest = verify_artifact_manifest(ROOT / "artifacts", ROOT / "artifacts/artifact_manifest.json")
    files = {item.get("name"): item.get("sha256") for item in manifest.get("files", [])}
    metrics = json.loads((ROOT / "artifacts/metrics.json").read_text(encoding="utf-8"))
    football = pd.read_csv(ROOT / "data/real_snapshot/football_epl_2023_24_snapshot.csv")
    tennis = pd.read_csv(ROOT / "data/real_snapshot/tennis_atp_2025_snapshot.csv")
    register_model(
        model_id="football-1n2-shadow", sport="football", version=settings.model_version, status="shadow",
        trained_until=pd.to_datetime(football["date"], utc=True).max(),
        dataset_hash=files.get("football_model.joblib"), metrics=metrics.get("football"),
    )
    register_model(
        model_id="tennis-elo-experimental", sport="tennis", version=settings.model_version, status="experimental",
        trained_until=pd.to_datetime(tennis["date"], utc=True).max(),
        dataset_hash=files.get("tennis_model.joblib"), metrics=metrics.get("tennis"),
    )
    print(json.dumps({"status": "ok", "models": list_models()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
