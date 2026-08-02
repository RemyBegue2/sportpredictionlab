from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.odds_data import bookmaker_h2h_markets


def main() -> int:
    p = argparse.ArgumentParser(description="Audit descriptif d'un export historique The Odds API.")
    p.add_argument("--input", default="data/odds_api/historical/historical_odds_long.csv")
    p.add_argument("--output", default="artifacts/historical_odds_audit.json")
    args = p.parse_args()
    source = ROOT / args.input
    if not source.exists():
        raise SystemExit(f"Fichier absent: {source}")
    rows = pd.read_csv(source)
    for col in ("commence_time", "market_last_update", "snapshot_time", "requested_snapshot_at"):
        if col in rows:
            rows[col] = pd.to_datetime(rows[col], utc=True, errors="coerce")
    markets = bookmaker_h2h_markets(rows)
    overrounds = np.array([m["overround"] for m in markets], dtype=float) if markets else np.array([])
    report = {
        "rows": int(len(rows)),
        "events": int(rows["event_id"].nunique()) if "event_id" in rows else 0,
        "sports": sorted(rows["sport_key"].dropna().astype(str).unique().tolist()) if "sport_key" in rows else [],
        "bookmakers": sorted(rows["bookmaker_key"].dropna().astype(str).unique().tolist()) if "bookmaker_key" in rows else [],
        "h2h_markets_complete": len(markets),
        "winamax_events": int(rows.loc[rows.get("bookmaker_key", pd.Series(dtype=str)).eq("winamax_fr"), "event_id"].nunique()) if "event_id" in rows else 0,
        "overround": {
            "median": float(np.median(overrounds)) if len(overrounds) else None,
            "p05": float(np.quantile(overrounds, .05)) if len(overrounds) else None,
            "p95": float(np.quantile(overrounds, .95)) if len(overrounds) else None,
        },
        "warning": "Descriptive audit only. Outcomes and leakage-safe model predictions are required for a performance claim.",
    }
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
