from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from sports_predictor.artifacts import write_artifact_manifest
from sports_predictor.football import FootballPredictor
from sports_predictor.market import market_log_loss
from sports_predictor.tennis import TennisPredictor

parser = argparse.ArgumentParser()
parser.add_argument("--football", default="data/processed/football_real.csv")
parser.add_argument("--tennis", default="data/processed/tennis_real.csv")
parser.add_argument("--artifacts", default="artifacts")
args = parser.parse_args()

out = Path(args.artifacts)
out.mkdir(parents=True, exist_ok=True)
football = pd.read_csv(args.football)
tennis = pd.read_csv(args.tennis)

football_model = FootballPredictor()
football_eval = football_model.fit(football)
football_path = out / "football_model.joblib"
football_model.save(football_path)

tennis_model = TennisPredictor()
tennis_eval = tennis_model.fit(tennis)
tennis_path = out / "tennis_model.joblib"
tennis_model.save(tennis_path)

metrics = {
    "mode": "real-data",
    "football": football_eval.to_dict(),
    "tennis": tennis_eval.to_dict(),
    "football_market_log_loss_full_dataset": market_log_loss(football),
    "notes": [
        "Final claims require multi-fold leakage-safe walk-forward, not this single split.",
        "Identical timestamps are processed as a batch.",
        "Odds are benchmark data, not automatically model inputs.",
    ],
}
metrics_path = out / "metrics.json"
metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
write_artifact_manifest([football_path, tennis_path, metrics_path], out / "artifact_manifest.json")
print(json.dumps(metrics, indent=2, ensure_ascii=False))
