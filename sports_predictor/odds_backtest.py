from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import math
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from sports_predictor.data_sources.the_odds_api import OddsApiClient


@dataclass(frozen=True)
class HistoricalPlan:
    requests: pd.DataFrame
    targets: pd.DataFrame
    estimated_credits: int
    markets: tuple[str, ...]
    bookmakers: tuple[str, ...]


def floor_timestamp(value: Any, *, interval_minutes: int = 5) -> pd.Timestamp:
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    ts = pd.to_datetime(value, utc=True, errors="raise")
    return ts.floor(f"{interval_minutes}min")


def build_historical_plan(
    events: pd.DataFrame,
    *,
    horizons_hours: Sequence[float] = (24.0, 6.0, 1.0),
    closing_minutes: int = 10,
    markets: Sequence[str] = ("h2h",),
    bookmakers: Sequence[str] = (
        "winamax_fr",
        "betclic_fr",
        "unibet_fr",
        "pmu_fr",
        "netbet_fr",
        "pinnacle",
    ),
    interval_minutes: int = 5,
) -> HistoricalPlan:
    required = {"sport_key", "event_id", "commence_time"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")
    target_rows: list[dict[str, Any]] = []
    for row in events.to_dict(orient="records"):
        commence = pd.to_datetime(row["commence_time"], utc=True, errors="raise")
        for horizon in horizons_hours:
            snapshot = floor_timestamp(commence - timedelta(hours=float(horizon)), interval_minutes=interval_minutes)
            target_rows.append({
                "sport_key": row["sport_key"],
                "event_id": row["event_id"],
                "commence_time": commence,
                "stage": f"t-{float(horizon):g}h",
                "snapshot_at": snapshot,
            })
        close_snapshot = floor_timestamp(commence - timedelta(minutes=int(closing_minutes)), interval_minutes=interval_minutes)
        target_rows.append({
            "sport_key": row["sport_key"],
            "event_id": row["event_id"],
            "commence_time": commence,
            "stage": f"close-{closing_minutes}m",
            "snapshot_at": close_snapshot,
        })
    targets = pd.DataFrame(target_rows).drop_duplicates(["sport_key", "event_id", "stage"])
    requests = targets[["sport_key", "snapshot_at"]].drop_duplicates().sort_values(["sport_key", "snapshot_at"]).reset_index(drop=True)
    requests["request_number"] = np.arange(1, len(requests) + 1)
    credits = OddsApiClient.estimate_quota_cost(
        markets=markets,
        bookmakers=bookmakers,
        historical=True,
        snapshot_count=len(requests),
    )
    return HistoricalPlan(
        requests=requests,
        targets=targets,
        estimated_credits=credits,
        markets=tuple(markets),
        bookmakers=tuple(bookmakers),
    )


def multiclass_metrics(
    y_true: Sequence[int],
    probabilities: np.ndarray,
    *,
    labels: Sequence[int],
) -> dict[str, float]:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if p.ndim != 2 or p.shape[0] != len(y):
        raise ValueError("Probability matrix shape mismatch")
    p = np.clip(p, 1e-12, 1.0)
    p /= p.sum(axis=1, keepdims=True)
    one_hot = np.eye(len(labels))[y]
    brier = float(np.mean(np.sum((p - one_hot) ** 2, axis=1)))
    accuracy = float(np.mean(np.argmax(p, axis=1) == y))
    result = {"n": int(len(y)), "log_loss": float(log_loss(y, p, labels=list(labels))), "brier": brier, "accuracy": accuracy}
    if len(labels) == 3:
        cumulative_p = np.cumsum(p, axis=1)[:, :-1]
        cumulative_y = np.cumsum(one_hot, axis=1)[:, :-1]
        result["rps"] = float(np.mean(np.sum((cumulative_p - cumulative_y) ** 2, axis=1) / 2.0))
    return result


def paired_log_loss_difference(
    y_true: Sequence[int],
    model_probabilities: np.ndarray,
    market_probabilities: np.ndarray,
    *,
    random_seed: int = 42,
    bootstrap_samples: int = 2000,
) -> dict[str, float]:
    y = np.asarray(y_true, dtype=int)
    model = np.clip(np.asarray(model_probabilities, dtype=float), 1e-12, 1.0)
    market = np.clip(np.asarray(market_probabilities, dtype=float), 1e-12, 1.0)
    if model.shape != market.shape or model.shape[0] != len(y):
        raise ValueError("Input shapes do not match")
    row = np.arange(len(y))
    model_loss = -np.log(model[row, y])
    market_loss = -np.log(market[row, y])
    diff = model_loss - market_loss
    rng = np.random.default_rng(random_seed)
    means = np.empty(bootstrap_samples, dtype=float)
    for i in range(bootstrap_samples):
        indices = rng.integers(0, len(diff), len(diff))
        means[i] = float(diff[indices].mean())
    low, high = np.quantile(means, [0.025, 0.975])
    return {
        "n": int(len(diff)),
        "mean_model_minus_market_log_loss": float(diff.mean()),
        "ci95_low": float(low),
        "ci95_high": float(high),
        "model_better_if_negative": True,
    }


def safe_threshold_gate(*, edge: float, lower_confidence_edge: float, minimum_edge: float = 0.03) -> bool:
    values = [edge, lower_confidence_edge, minimum_edge]
    if not all(math.isfinite(float(x)) for x in values):
        return False
    return float(edge) >= float(minimum_edge) and float(lower_confidence_edge) > 0.0
