from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from sports_predictor.artifacts import write_artifact_manifest
from sports_predictor.football import FootballPredictor
from sports_predictor.tennis import TennisPredictor

out = ROOT / "artifacts"
out.mkdir(exist_ok=True)
football = pd.read_csv(ROOT / "data/real_snapshot/football_epl_2023_24_snapshot.csv")
tennis = pd.read_csv(ROOT / "data/real_snapshot/tennis_atp_2025_snapshot.csv")

football_model = FootballPredictor()
football_eval = football_model.fit(football)
football_path = out / "football_model.joblib"
football_model.save(football_path)

# The bundled tennis snapshot contains only two tournament timestamps. A valid
# train/calibration/test split is impossible, so the application deliberately
# serves the transparent Elo component without claiming calibrated performance.
tennis_model = TennisPredictor()
tennis_eval = tennis_model.fit_elo_only(tennis)
tennis_path = out / "tennis_model.joblib"
tennis_model.save(tennis_path)

metrics = {
    "mode": "real-data-snapshot-smoke-test",
    "warning": "Snapshot is for application verification, not performance conclusions.",
    "football": football_eval.to_dict(),
    "tennis": tennis_eval.to_dict(),
    "data": {
        "football_rows": len(football),
        "football_distinct_timestamps": int(pd.to_datetime(football["date"]).nunique()),
        "tennis_rows": len(tennis),
        "tennis_distinct_tournament_timestamps": int(pd.to_datetime(tennis["date"]).nunique()),
    },
    "audit_decisions": [
        "Identical timestamps are processed as a batch to prevent same-day/tournament leakage.",
        "Tennis snapshot uses Elo-only serving because two timestamps cannot support calibration.",
    ],
}
metrics_path = out / "metrics.json"
metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
write_artifact_manifest([football_path, tennis_path, metrics_path], out / "artifact_manifest.json")
print(json.dumps(metrics, indent=2, ensure_ascii=False))
