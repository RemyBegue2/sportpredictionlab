from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Any
import math

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss

from .common import (
    binary_brier,
    expected_calibration_error,
    multiclass_brier,
    ranked_probability_score,
)
from .football import FootballPredictor
from .tennis import TennisPredictor

EPS = 1e-12


@dataclass
class BacktestFold:
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n_train: int
    n_test: int
    metrics: dict[str, float]


def _block_bootstrap_mean_ci(values: np.ndarray, block_size: int = 10,
                             n_boot: int = 1500, seed: int = 42) -> tuple[float, float]:
    """Moving-block bootstrap CI for the mean of temporally dependent losses."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < 4:
        return float("nan"), float("nan")
    block_size = max(1, min(block_size, n))
    starts = np.arange(0, n - block_size + 1)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    n_blocks = math.ceil(n / block_size)
    for i in range(n_boot):
        chosen = rng.choice(starts, size=n_blocks, replace=True)
        sample = np.concatenate([x[s:s + block_size] for s in chosen])[:n]
        means[i] = sample.mean()
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def _football_targets(df: pd.DataFrame) -> np.ndarray:
    return np.where(df["home_goals"].to_numpy() > df["away_goals"].to_numpy(), 2,
                    np.where(df["home_goals"].to_numpy() == df["away_goals"].to_numpy(), 1, 0))


def _date_boundaries(df: pd.DataFrame) -> np.ndarray:
    dates = df["date"].to_numpy()
    changes = np.flatnonzero(dates[1:] != dates[:-1]) + 1
    return np.concatenate(([0], changes, [len(df)])).astype(int)


def _initial_boundary(boundaries: np.ndarray, requested: int, n: int) -> int:
    candidates = boundaries[(boundaries >= 30) & (boundaries < n)]
    if len(candidates) == 0:
        raise ValueError("Not enough distinct timestamp groups for backtesting")
    before = candidates[candidates <= requested]
    return int(before[-1] if len(before) else candidates[0])


def _horizon_boundary(boundaries: np.ndarray, start: int, horizon: int, n: int) -> int:
    target = min(start + horizon, n)
    candidates = boundaries[(boundaries > start) & (boundaries <= target)]
    if len(candidates):
        return int(candidates[-1])
    later = boundaries[boundaries > start]
    return int(later[0]) if len(later) else n


def backtest_football(data: pd.DataFrame, *, initial_train: int = 600,
                      horizon: int = 100, max_folds: int = 6,
                      model_factory: Callable[[], FootballPredictor] = FootballPredictor) -> dict[str, Any]:
    if horizon <= 0 or max_folds <= 0:
        raise ValueError("horizon and max_folds must be positive")
    df = data.copy()
    df["date"] = pd.to_datetime(df["date"], utc=True, format="mixed")
    df = df.sort_values("date", kind="stable").reset_index(drop=True)
    if initial_train < 30 or initial_train >= len(df):
        raise ValueError("initial_train must be >=30 and smaller than dataset")
    boundaries = _date_boundaries(df)
    start = _initial_boundary(boundaries, initial_train, len(df))

    all_y: list[int] = []
    all_p: list[list[float]] = []
    all_base: list[list[float]] = []
    folds: list[BacktestFold] = []
    for fold in range(max_folds):
        if start >= len(df):
            break
        end = _horizon_boundary(boundaries, start, horizon, len(df))
        history = df.iloc[:start].copy()
        test = df.iloc[start:end].copy()
        model = model_factory()
        model.fit(history)
        prior = np.bincount(_football_targets(history), minlength=3).astype(float)
        prior = prior / prior.sum()
        fold_y: list[int] = []
        fold_p: list[list[float]] = []
        rolling_history = history.copy()

        # Predict an entire timestamp group before revealing any result in it.
        for _, day_group in test.groupby("date", sort=False):
            fixtures = day_group[["date", "league", "home_team", "away_team"]].copy()
            predictions = model.predict_matches(rolling_history, fixtures)
            for row, pred in zip(day_group.itertuples(index=False), predictions):
                fold_p.append([pred["away_win"], pred["draw"], pred["home_win"]])
                fold_y.append(2 if row.home_goals > row.away_goals else
                              (1 if row.home_goals == row.away_goals else 0))
            rolling_history = pd.concat([rolling_history, day_group], ignore_index=True)

        y = np.asarray(fold_y, dtype=int)
        p_fold = np.asarray(fold_p, dtype=float)
        base = np.tile(prior, (len(y), 1))
        metrics = {
            "log_loss": float(log_loss(y, p_fold, labels=[0, 1, 2])),
            "naive_log_loss": float(log_loss(y, base, labels=[0, 1, 2])),
            "brier": multiclass_brier(y, p_fold, 3),
            "rps": ranked_probability_score(y, p_fold),
            "accuracy": float(accuracy_score(y, p_fold.argmax(axis=1))),
            "ece": expected_calibration_error(y, p_fold),
        }
        folds.append(BacktestFold(
            fold=fold,
            train_start=str(df.iloc[0].date), train_end=str(df.iloc[start - 1].date),
            test_start=str(df.iloc[start].date), test_end=str(df.iloc[end - 1].date),
            n_train=start, n_test=len(y), metrics=metrics,
        ))
        all_y.extend(y.tolist())
        all_p.extend(p_fold.tolist())
        all_base.extend(base.tolist())
        start = end

    if not all_y:
        raise ValueError("No leakage-safe football backtest fold could be formed")
    y = np.asarray(all_y, dtype=int)
    p_all = np.asarray(all_p, dtype=float)
    base_all = np.asarray(all_base, dtype=float)
    idx = np.arange(len(y))
    delta = -np.log(np.clip(p_all[idx, y], EPS, 1.0)) + np.log(np.clip(base_all[idx, y], EPS, 1.0))
    ci = _block_bootstrap_mean_ci(delta, block_size=max(3, min(horizon // 4, 20)))
    return {
        "sport": "football",
        "protocol": "external expanding-window; identical timestamps predicted as a batch",
        "n_predictions": len(y),
        "folds": [asdict(f) for f in folds],
        "aggregate": {
            "log_loss": float(log_loss(y, p_all, labels=[0, 1, 2])),
            "naive_log_loss": float(log_loss(y, base_all, labels=[0, 1, 2])),
            "brier": multiclass_brier(y, p_all, 3),
            "rps": ranked_probability_score(y, p_all),
            "accuracy": float(accuracy_score(y, p_all.argmax(axis=1))),
            "ece": expected_calibration_error(y, p_all),
            "mean_log_loss_delta_vs_naive": float(delta.mean()),
            "delta_95pct_block_bootstrap": list(ci),
        },
    }


def backtest_tennis(data: pd.DataFrame, *, initial_train: int = 1500,
                    horizon: int = 250, max_folds: int = 6,
                    model_factory: Callable[[], TennisPredictor] = TennisPredictor) -> dict[str, Any]:
    if horizon <= 0 or max_folds <= 0:
        raise ValueError("horizon and max_folds must be positive")
    df = data.copy()
    df["date"] = pd.to_datetime(df["date"], utc=True, format="mixed")
    df = df.sort_values("date", kind="stable").reset_index(drop=True)
    if initial_train < 30 or initial_train >= len(df):
        raise ValueError("initial_train must be >=30 and smaller than dataset")
    boundaries = _date_boundaries(df)
    start = _initial_boundary(boundaries, initial_train, len(df))

    all_y: list[int] = []
    all_p: list[float] = []
    folds: list[BacktestFold] = []
    for fold in range(max_folds):
        if start >= len(df):
            break
        end = _horizon_boundary(boundaries, start, horizon, len(df))
        history = df.iloc[:start].copy()
        test = df.iloc[start:end].copy()
        model = model_factory()
        model.fit(history)
        rolling_history = history.copy()
        fold_y: list[int] = []
        fold_p: list[float] = []

        for _, tournament_group in test.groupby("date", sort=False):
            fixtures = []
            targets = []
            for global_index, row in tournament_group.iterrows():
                normal = (global_index % 2 == 0)
                fixtures.append({
                    "date": row["date"],
                    "tour": str(row.get("tour", "ATP")),
                    "surface": str(row["surface"]),
                    "tournament_level": str(row["tournament_level"]),
                    "best_of": int(row.get("best_of", 3)),
                    "player_1": str(row["winner_name"] if normal else row["loser_name"]),
                    "player_2": str(row["loser_name"] if normal else row["winner_name"]),
                    "p1_rank": row.get("winner_rank", np.nan) if normal else row.get("loser_rank", np.nan),
                    "p2_rank": row.get("loser_rank", np.nan) if normal else row.get("winner_rank", np.nan),
                    "p1_rank_points": row.get("winner_rank_points", np.nan) if normal else row.get("loser_rank_points", np.nan),
                    "p2_rank_points": row.get("loser_rank_points", np.nan) if normal else row.get("winner_rank_points", np.nan),
                })
                targets.append(1 if normal else 0)
            probs = model.predict_matches(rolling_history, pd.DataFrame(fixtures))
            fold_p.extend(np.asarray(probs, dtype=float).tolist())
            fold_y.extend(targets)
            rolling_history = pd.concat([rolling_history, tournament_group], ignore_index=True)

        y = np.asarray(fold_y, dtype=int)
        p_fold = np.asarray(fold_p, dtype=float)
        metrics = {
            "log_loss": float(log_loss(y, p_fold, labels=[0, 1])),
            "naive_log_loss": float(log_loss(y, np.full(len(y), 0.5), labels=[0, 1])),
            "brier": binary_brier(y, p_fold),
            "accuracy": float(accuracy_score(y, p_fold >= 0.5)),
            "ece": expected_calibration_error(y, p_fold),
        }
        folds.append(BacktestFold(
            fold, str(df.iloc[0].date), str(df.iloc[start - 1].date),
            str(df.iloc[start].date), str(df.iloc[end - 1].date), start, len(y), metrics,
        ))
        all_y.extend(y.tolist())
        all_p.extend(p_fold.tolist())
        start = end

    if not all_y:
        raise ValueError("No leakage-safe tennis backtest fold could be formed")
    y = np.asarray(all_y, dtype=int)
    p_all = np.asarray(all_p, dtype=float)
    chosen = np.where(y == 1, p_all, 1 - p_all)
    delta = -np.log(np.clip(chosen, EPS, 1.0)) + math.log(0.5)
    ci = _block_bootstrap_mean_ci(delta, block_size=max(3, min(horizon // 4, 20)))
    return {
        "sport": "tennis",
        "protocol": "external expanding-window; identical tournament timestamps predicted as a batch",
        "n_predictions": len(y),
        "folds": [asdict(f) for f in folds],
        "aggregate": {
            "log_loss": float(log_loss(y, p_all, labels=[0, 1])),
            "naive_log_loss": float(log_loss(y, np.full(len(y), 0.5), labels=[0, 1])),
            "brier": binary_brier(y, p_all),
            "accuracy": float(accuracy_score(y, p_all >= 0.5)),
            "ece": expected_calibration_error(y, p_all),
            "mean_log_loss_delta_vs_naive": float(delta.mean()),
            "delta_95pct_block_bootstrap": list(ci),
        },
    }
