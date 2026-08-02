from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss


def devig_three_way(home_odds, draw_odds, away_odds) -> np.ndarray:
    odds = np.column_stack([away_odds, draw_odds, home_odds]).astype(float)
    inv = 1.0 / np.clip(odds, 1.001, None)
    return inv / inv.sum(axis=1, keepdims=True)


def market_log_loss(df: pd.DataFrame) -> float | None:
    cols = ["market_home_odds", "market_draw_odds", "market_away_odds"]
    if any(c not in df for c in cols): return None
    mask = df[cols].notna().all(axis=1)
    if not mask.any(): return None
    y = np.where(df.loc[mask, "home_goals"] > df.loc[mask, "away_goals"], 2,
                 np.where(df.loc[mask, "home_goals"] == df.loc[mask, "away_goals"], 1, 0))
    p = devig_three_way(df.loc[mask, "market_home_odds"], df.loc[mask, "market_draw_odds"], df.loc[mask, "market_away_odds"])
    return float(log_loss(y, p, labels=[0,1,2]))
