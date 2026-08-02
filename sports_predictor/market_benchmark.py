from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from .backtest import _block_bootstrap_mean_ci
from .common import expected_calibration_error, multiclass_brier, ranked_probability_score

EPS = 1e-12
OUTCOME_ORDER = ("away", "draw", "home")


@dataclass(frozen=True)
class BenchmarkPolicy:
    minimum_predictions: int = 500
    exploratory_predictions: int = 200
    n_folds: int = 5
    minimum_train: int = 150
    blend_grid_size: int = 21
    bootstrap_samples: int = 1500
    block_size: int = 20


@dataclass(frozen=True)
class TemporalAudit:
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    violations: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _probability_matrix(frame: pd.DataFrame, prefix: str) -> np.ndarray:
    columns = [f"{prefix}_{name}" for name in OUTCOME_ORDER]
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"Missing probability columns for {prefix}: {missing}")
    values = frame[columns].to_numpy(dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("Expected a 3-outcome probability matrix")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"Invalid probabilities for {prefix}")
    totals = values.sum(axis=1, keepdims=True)
    if (totals <= 0).any():
        raise ValueError(f"Zero probability sum for {prefix}")
    values = np.clip(values / totals, EPS, 1.0)
    return values / values.sum(axis=1, keepdims=True)


def temporal_integrity_audit(frame: pd.DataFrame) -> tuple[pd.DataFrame, TemporalAudit]:
    required = {"commence_time", "prediction_created_at", "odds_observed_at"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing temporal columns: {sorted(missing)}")
    checked = frame.copy()
    for col in sorted(required | ({"result_available_at"} if "result_available_at" in checked.columns else set())):
        checked[col] = pd.to_datetime(checked[col], utc=True, errors="coerce")
    violations = {
        "missing_timestamp": int(checked[list(required)].isna().any(axis=1).sum()),
        "odds_after_prediction": int((checked["odds_observed_at"] > checked["prediction_created_at"]).fillna(False).sum()),
        "prediction_at_or_after_start": int((checked["prediction_created_at"] >= checked["commence_time"]).fillna(False).sum()),
        "odds_at_or_after_start": int((checked["odds_observed_at"] >= checked["commence_time"]).fillna(False).sum()),
    }
    invalid = checked[list(required)].isna().any(axis=1)
    invalid |= checked["odds_observed_at"] > checked["prediction_created_at"]
    invalid |= checked["prediction_created_at"] >= checked["commence_time"]
    invalid |= checked["odds_observed_at"] >= checked["commence_time"]
    if "result_available_at" in checked.columns:
        result_violation = (checked["result_available_at"] <= checked["prediction_created_at"]).fillna(False)
        violations["result_available_before_prediction"] = int(result_violation.sum())
        invalid |= result_violation
    accepted = checked.loc[~invalid].copy()
    audit = TemporalAudit(len(checked), len(accepted), int(invalid.sum()), violations)
    return accepted, audit


def _chronological_folds(frame: pd.DataFrame, *, n_folds: int, minimum_train: int) -> list[tuple[np.ndarray, np.ndarray]]:
    ordered = frame.sort_values("commence_time", kind="stable").reset_index(drop=True)
    groups = ordered["commence_time"].dt.floor("D")
    unique_groups = pd.Index(groups.drop_duplicates())
    if len(ordered) <= minimum_train or len(unique_groups) < 3:
        return []
    train_groups = max(1, np.searchsorted(np.cumsum(groups.value_counts(sort=False).to_numpy()), minimum_train) + 1)
    remaining_groups = len(unique_groups) - train_groups
    fold_count = min(max(1, n_folds), remaining_groups)
    if fold_count <= 0:
        return []
    chunks = np.array_split(np.arange(train_groups, len(unique_groups)), fold_count)
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for chunk in chunks:
        if len(chunk) == 0:
            continue
        first_test_group = int(chunk[0])
        train_mask = groups.isin(unique_groups[:first_test_group]).to_numpy()
        test_mask = groups.isin(unique_groups[chunk]).to_numpy()
        train_idx = np.flatnonzero(train_mask)
        test_idx = np.flatnonzero(test_mask)
        if len(train_idx) >= minimum_train and len(test_idx):
            folds.append((train_idx, test_idx))
    return folds


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "log_loss": float(log_loss(y, p, labels=[0, 1, 2])),
        "brier": multiclass_brier(y, p, 3),
        "rps": ranked_probability_score(y, p),
        "accuracy": float(np.mean(np.argmax(p, axis=1) == y)),
        "ece": expected_calibration_error(y, p),
    }


def _best_blend_weight(y: np.ndarray, model: np.ndarray, market: np.ndarray, grid_size: int) -> float:
    weights = np.linspace(0.0, 1.0, max(2, int(grid_size)))
    losses = []
    for weight in weights:
        blended = weight * model + (1.0 - weight) * market
        losses.append(log_loss(y, blended, labels=[0, 1, 2]))
    return float(weights[int(np.argmin(losses))])


def _paired_delta(y: np.ndarray, left: np.ndarray, right: np.ndarray, *, block_size: int, bootstrap_samples: int) -> dict[str, Any]:
    idx = np.arange(len(y))
    delta = -np.log(np.clip(left[idx, y], EPS, 1.0)) + np.log(np.clip(right[idx, y], EPS, 1.0))
    low, high = _block_bootstrap_mean_ci(delta, block_size=block_size, n_boot=bootstrap_samples)
    return {
        "n": int(len(delta)),
        "mean_left_minus_right_log_loss": float(delta.mean()),
        "ci95_low": low,
        "ci95_high": high,
        "left_better_if_negative": True,
    }


def _promotion_verdict(n: int, comparison: dict[str, Any], policy: BenchmarkPolicy, *, fold_count: int) -> dict[str, str]:
    if fold_count == 0:
        return {"status": "not_evaluable", "reason": "no expanding-window fold could be formed; descriptive metrics are not a promotion test"}
    if n < policy.exploratory_predictions:
        return {"status": "not_evaluable", "reason": f"only {n} accepted predictions; at least {policy.exploratory_predictions} are required for an exploratory signal"}
    if n < policy.minimum_predictions:
        return {"status": "exploratory", "reason": f"{n} predictions provide only a preliminary signal; promotion requires at least {policy.minimum_predictions}"}
    high = comparison.get("ci95_high")
    if high is not None and np.isfinite(high) and high < 0:
        return {"status": "preliminary_go", "reason": "model log-loss is lower than Winamax with a block-bootstrap interval below zero"}
    return {"status": "no_go", "reason": "the model has not demonstrated a robust out-of-sample advantage over Winamax"}


def run_market_benchmark(frame: pd.DataFrame, *, policy: BenchmarkPolicy | None = None) -> dict[str, Any]:
    policy = policy or BenchmarkPolicy()
    required = {"result_class", "event_id", "commence_time", "prediction_created_at", "odds_observed_at"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing benchmark columns: {sorted(missing)}")
    clean, temporal_audit = temporal_integrity_audit(frame)
    clean = clean.sort_values("commence_time", kind="stable").reset_index(drop=True)
    for prefix in ("model", "winamax", "consensus"):
        matrix = _probability_matrix(clean, prefix)
        clean[[f"_{prefix}_{i}" for i in range(3)]] = matrix
    y = clean["result_class"].to_numpy(dtype=int)
    if not set(np.unique(y)).issubset({0, 1, 2}):
        raise ValueError("result_class must use 0=away, 1=draw, 2=home")
    model = clean[[f"_model_{i}" for i in range(3)]].to_numpy(float)
    winamax = clean[[f"_winamax_{i}" for i in range(3)]].to_numpy(float)
    consensus = clean[[f"_consensus_{i}" for i in range(3)]].to_numpy(float)
    folds = _chronological_folds(clean, n_folds=policy.n_folds, minimum_train=policy.minimum_train)
    fold_reports: list[dict[str, Any]] = []
    test_indices: list[int] = []
    blend_predictions: list[np.ndarray] = []
    for fold_number, (train_idx, test_idx) in enumerate(folds, 1):
        weight = _best_blend_weight(y[train_idx], model[train_idx], consensus[train_idx], policy.blend_grid_size)
        blended = weight * model[test_idx] + (1.0 - weight) * consensus[test_idx]
        fold_reports.append({
            "fold": fold_number,
            "train_start": clean.iloc[train_idx[0]]["commence_time"].isoformat(),
            "train_end": clean.iloc[train_idx[-1]]["commence_time"].isoformat(),
            "test_start": clean.iloc[test_idx[0]]["commence_time"].isoformat(),
            "test_end": clean.iloc[test_idx[-1]]["commence_time"].isoformat(),
            "n_train": int(len(train_idx)),
            "n_test": int(len(test_idx)),
            "blend_model_weight": weight,
            "model": _metrics(y[test_idx], model[test_idx]),
            "winamax": _metrics(y[test_idx], winamax[test_idx]),
            "consensus": _metrics(y[test_idx], consensus[test_idx]),
            "blend": _metrics(y[test_idx], blended),
        })
        test_indices.extend(test_idx.tolist())
        blend_predictions.append(blended)

    if test_indices:
        test_idx = np.asarray(test_indices, dtype=int)
        blend = np.vstack(blend_predictions)
        y_eval = y[test_idx]
        model_eval, winamax_eval, consensus_eval = model[test_idx], winamax[test_idx], consensus[test_idx]
    else:
        test_idx = np.arange(len(clean))
        y_eval, model_eval, winamax_eval, consensus_eval = y, model, winamax, consensus
        blend = consensus_eval.copy()

    comparisons = {
        "model_vs_winamax": _paired_delta(y_eval, model_eval, winamax_eval, block_size=policy.block_size, bootstrap_samples=policy.bootstrap_samples) if len(y_eval) >= 4 else None,
        "model_vs_consensus": _paired_delta(y_eval, model_eval, consensus_eval, block_size=policy.block_size, bootstrap_samples=policy.bootstrap_samples) if len(y_eval) >= 4 else None,
        "blend_vs_winamax": _paired_delta(y_eval, blend, winamax_eval, block_size=policy.block_size, bootstrap_samples=policy.bootstrap_samples) if len(y_eval) >= 4 else None,
    }
    aggregate = {
        "model": _metrics(y_eval, model_eval) if len(y_eval) else None,
        "winamax": _metrics(y_eval, winamax_eval) if len(y_eval) else None,
        "consensus": _metrics(y_eval, consensus_eval) if len(y_eval) else None,
        "blend": _metrics(y_eval, blend) if len(y_eval) else None,
    }
    clv = None
    if {"taken_odds", "closing_odds"}.issubset(clean.columns):
        selected = clean.iloc[test_idx].copy()
        taken = pd.to_numeric(selected["taken_odds"], errors="coerce")
        closing = pd.to_numeric(selected["closing_odds"], errors="coerce")
        valid = taken.gt(1.0) & closing.gt(1.0)
        if valid.any():
            log_clv = np.log(taken[valid].to_numpy(float) / closing[valid].to_numpy(float))
            clv = {"n": int(valid.sum()), "mean_log_clv": float(log_clv.mean()), "median_log_clv": float(np.median(log_clv)), "positive_rate": float(np.mean(log_clv > 0))}
    comparison = comparisons["model_vs_winamax"] or {"ci95_high": None}
    return {
        "protocol": "expanding-window folds; blend weight learned only on prior rows; identical match dates stay in the same fold",
        "outcome_order": list(OUTCOME_ORDER),
        "policy": asdict(policy),
        "temporal_audit": temporal_audit.to_dict(),
        "accepted_rows": int(len(clean)),
        "evaluated_rows": int(len(y_eval)),
        "folds": fold_reports,
        "aggregate": aggregate,
        "comparisons": comparisons,
        "closing_line_value": clv,
        "verdict": _promotion_verdict(len(y_eval), comparison, policy, fold_count=len(folds)),
        "limitations": [
            "ROI is deliberately secondary to proper scoring rules and closing-line value.",
            "A preliminary_go is not a claim of future profitability.",
            "Rows rejected by the temporal audit are excluded rather than repaired silently.",
        ],
    }


def benchmark_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {"status": "not_run", "evaluated_rows": 0, "message": "No real historical benchmark has been completed."}
    verdict = report.get("verdict") or {}
    comparison = (report.get("comparisons") or {}).get("model_vs_winamax") or {}
    return {
        "status": verdict.get("status", "unknown"),
        "reason": verdict.get("reason"),
        "evaluated_rows": report.get("evaluated_rows", 0),
        "model_vs_winamax_log_loss_delta": comparison.get("mean_left_minus_right_log_loss"),
        "ci95": [comparison.get("ci95_low"), comparison.get("ci95_high")],
        "clv": report.get("closing_line_value"),
    }
