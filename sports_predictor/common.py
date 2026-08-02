from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
import json
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.metrics import accuracy_score, log_loss


EPS = 1e-12


def chronological_split_indices(n: int, train_frac: float = 0.65, calibration_frac: float = 0.15) -> tuple[slice, slice, slice]:
    if n < 30:
        raise ValueError("At least 30 chronological observations are required.")
    train_end = max(10, int(n * train_frac))
    cal_end = max(train_end + 5, int(n * (train_frac + calibration_frac)))
    cal_end = min(cal_end, n - 5)
    return slice(0, train_end), slice(train_end, cal_end), slice(cal_end, n)


def chronological_group_split_indices(
    dates: Sequence,
    train_frac: float = 0.65,
    calibration_frac: float = 0.15,
    min_train: int = 10,
    min_calibration: int = 5,
    min_test: int = 5,
) -> tuple[slice, slice, slice]:
    """Chronological split that never cuts through an identical timestamp group.

    Many sports archives expose only a match day or tournament start date. A row-level
    split can therefore train on one result while evaluating another event that has the
    same timestamp. Boundaries are selected only between timestamp groups.
    """
    ts = pd.Series(pd.to_datetime(list(dates), utc=True, errors="raise"))
    n = len(ts)
    if n < min_train + min_calibration + min_test:
        raise ValueError("Not enough observations for grouped train/calibration/test split.")
    if not ts.is_monotonic_increasing:
        raise ValueError("Dates must be sorted before grouped chronological splitting.")

    change_points = np.flatnonzero(ts.to_numpy()[1:] != ts.to_numpy()[:-1]) + 1
    boundaries = np.concatenate(([0], change_points, [n])).astype(int)

    train_candidates = boundaries[(boundaries >= min_train) &
                                  (boundaries <= n - min_calibration - min_test)]
    if len(train_candidates) == 0:
        raise ValueError("Too few distinct timestamps for a leakage-safe training split.")
    train_target = int(n * train_frac)
    train_end = int(train_candidates[np.argmin(np.abs(train_candidates - train_target))])

    cal_candidates = boundaries[(boundaries >= train_end + min_calibration) &
                                (boundaries <= n - min_test)]
    if len(cal_candidates) == 0:
        raise ValueError("Too few distinct timestamps for a leakage-safe calibration/test split.")
    cal_target = int(n * (train_frac + calibration_frac))
    cal_end = int(cal_candidates[np.argmin(np.abs(cal_candidates - cal_target))])
    return slice(0, train_end), slice(train_end, cal_end), slice(cal_end, n)


def multiclass_brier(y_true: np.ndarray, probs: np.ndarray, n_classes: int) -> float:
    one_hot = np.eye(n_classes)[np.asarray(y_true, dtype=int)]
    return float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))


def binary_brier(y_true: np.ndarray, probs: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probs, dtype=float)
    return float(np.mean((p - y) ** 2))


def expected_calibration_error(y_true: np.ndarray, probs: np.ndarray, n_bins: int = 10) -> float:
    """Top-label ECE for multiclass, standard ECE for binary."""
    y = np.asarray(y_true)
    p = np.asarray(probs)
    if p.ndim == 2:
        confidence = p.max(axis=1)
        correct = (p.argmax(axis=1) == y).astype(float)
    else:
        confidence = np.maximum(p, 1 - p)
        pred = (p >= 0.5).astype(int)
        correct = (pred == y).astype(float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (confidence > lo) & (confidence <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(ece)


def ranked_probability_score(y_true: np.ndarray, probs: np.ndarray) -> float:
    """RPS for ordered classes. Football class order must be away/draw/home or home/draw/away consistently."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(probs, dtype=float)
    one_hot = np.eye(p.shape[1])[y]
    return float(np.mean(np.sum((np.cumsum(p, axis=1)[:, :-1] - np.cumsum(one_hot, axis=1)[:, :-1]) ** 2, axis=1)))


def _softmax_from_log_probs(log_probs: np.ndarray, temperature: float) -> np.ndarray:
    z = log_probs / temperature
    z = z - z.max(axis=1, keepdims=True)
    exp_z = np.exp(z)
    return exp_z / exp_z.sum(axis=1, keepdims=True)


def fit_temperature_multiclass(probs: np.ndarray, y_true: np.ndarray) -> float:
    log_probs = np.log(np.clip(probs, EPS, 1.0))
    y = np.asarray(y_true, dtype=int)

    def objective(log_t: float) -> float:
        t = float(np.exp(log_t))
        return log_loss(y, _softmax_from_log_probs(log_probs, t), labels=list(range(probs.shape[1])))

    result = minimize_scalar(objective, bounds=(math.log(0.25), math.log(5.0)), method="bounded")
    return float(np.exp(result.x))


def apply_temperature_multiclass(probs: np.ndarray, temperature: float) -> np.ndarray:
    return _softmax_from_log_probs(np.log(np.clip(probs, EPS, 1.0)), temperature)


def fit_temperature_binary(probs: np.ndarray, y_true: np.ndarray) -> float:
    p = np.clip(np.asarray(probs, dtype=float), EPS, 1 - EPS)
    logits = np.log(p / (1 - p))
    y = np.asarray(y_true, dtype=int)

    def objective(log_t: float) -> float:
        t = float(np.exp(log_t))
        q = 1.0 / (1.0 + np.exp(-logits / t))
        return log_loss(y, q, labels=[0, 1])

    result = minimize_scalar(objective, bounds=(math.log(0.25), math.log(5.0)), method="bounded")
    return float(np.exp(result.x))


def apply_temperature_binary(probs: np.ndarray, temperature: float) -> np.ndarray:
    p = np.clip(np.asarray(probs, dtype=float), EPS, 1 - EPS)
    logits = np.log(p / (1 - p))
    return 1.0 / (1.0 + np.exp(-logits / temperature))


def optimize_blend_multiclass(stat_probs: np.ndarray, ml_probs: np.ndarray, y_true: np.ndarray, min_z: float = 1.645) -> float:
    """Choose an ML weight only when its calibration-window gain clears a one-sided guardrail."""
    y = np.asarray(y_true, dtype=int)
    grid = np.linspace(0.0, 1.0, 101)
    losses = [log_loss(y, a * ml_probs + (1 - a) * stat_probs, labels=list(range(ml_probs.shape[1]))) for a in grid]
    alpha = float(grid[int(np.argmin(losses))])
    if alpha == 0.0:
        return 0.0
    blend = alpha * ml_probs + (1 - alpha) * stat_probs
    idx = np.arange(len(y))
    loss_delta = -np.log(np.clip(blend[idx, y], EPS, 1.0)) + np.log(np.clip(stat_probs[idx, y], EPS, 1.0))
    se = float(loss_delta.std(ddof=1) / np.sqrt(len(loss_delta))) if len(loss_delta) > 1 else float("inf")
    z_improvement = float(-loss_delta.mean() / se) if se > 0 and np.isfinite(se) else 0.0
    return alpha if z_improvement >= min_z else 0.0


def optimize_blend_binary(stat_probs: np.ndarray, ml_probs: np.ndarray, y_true: np.ndarray, min_z: float = 1.645) -> float:
    """Choose an ML weight only when its calibration-window gain clears a one-sided guardrail."""
    y = np.asarray(y_true, dtype=int)
    grid = np.linspace(0.0, 1.0, 101)
    losses = [log_loss(y, a * ml_probs + (1 - a) * stat_probs, labels=[0, 1]) for a in grid]
    alpha = float(grid[int(np.argmin(losses))])
    if alpha == 0.0:
        return 0.0
    blend = alpha * ml_probs + (1 - alpha) * stat_probs
    chosen = np.where(y == 1, blend, 1 - blend)
    baseline = np.where(y == 1, stat_probs, 1 - stat_probs)
    loss_delta = -np.log(np.clip(chosen, EPS, 1.0)) + np.log(np.clip(baseline, EPS, 1.0))
    se = float(loss_delta.std(ddof=1) / np.sqrt(len(loss_delta))) if len(loss_delta) > 1 else float("inf")
    z_improvement = float(-loss_delta.mean() / se) if se > 0 and np.isfinite(se) else 0.0
    return alpha if z_improvement >= min_z else 0.0


def write_json(path: str | Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def validate_date_order(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], utc=True, errors="raise")
    return out.sort_values(date_col, kind="stable").reset_index(drop=True)


def safe_days_between(current: pd.Timestamp, previous: pd.Timestamp | None, default: float = 14.0) -> float:
    if previous is None or pd.isna(previous):
        return default
    return float(max(0, (current - previous).total_seconds() / 86400.0))


@dataclass
class Evaluation:
    metrics: dict[str, float]
    n_test: int

    def to_dict(self) -> dict:
        return {"n_test": self.n_test, **self.metrics}
