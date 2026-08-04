from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from .common import (
    apply_temperature_binary,
    apply_temperature_multiclass,
    binary_brier,
    expected_calibration_error,
    fit_temperature_binary,
    fit_temperature_multiclass,
    multiclass_brier,
)
from .football import FootballPredictor
from .tennis import TennisPredictor


@dataclass(frozen=True)
class ChallengerFactoryLimits:
    minimum_rows: int = 120
    minimum_distinct_dates: int = 12
    maximum_models_per_sport: int = 4
    maximum_configurations_per_model: int = 20
    maximum_folds: int = 5
    holdout_fraction: float = 0.20
    calibration_fraction: float = 0.20
    log_loss_improvement_required: float = 0.002
    ece_tolerance: float = 0.015


FOOTBALL_FEATURES = (
    "elo_diff",
    "elo_home_prob",
    "home_attack_form",
    "home_defence_form",
    "away_attack_form",
    "away_defence_form",
    "league_home_goal_rate",
    "league_away_goal_rate",
    "home_rest_days",
    "away_rest_days",
    "home_matches_seen",
    "away_matches_seen",
)

TENNIS_FEATURES = (
    "rank_log_advantage",
    "rank_points_diff",
    "global_elo_diff",
    "surface_elo_diff",
    "combined_elo_diff",
    "elo_probability",
    "recent_form_diff",
    "p1_inactivity_days",
    "p2_inactivity_days",
    "p1_matches_seen",
    "p2_matches_seen",
    "best_of",
)


def _normalise_frame_for_hash(frame: pd.DataFrame) -> bytes:
    ordered = frame.copy()
    ordered.columns = [str(column) for column in ordered.columns]
    sort_columns = [column for column in ("date", "home_team", "away_team", "winner_name", "loser_name") if column in ordered]
    if sort_columns:
        ordered = ordered.sort_values(sort_columns, kind="stable")
    ordered = ordered.reset_index(drop=True)
    return ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")


def dataset_snapshot(frame: pd.DataFrame, *, sport: str, source: str) -> dict[str, Any]:
    digest = sha256(_normalise_frame_for_hash(frame)).hexdigest()
    dates = pd.to_datetime(frame.get("date"), utc=True, errors="coerce")
    cutoff = dates.max()
    return {
        "dataset_id": f"DS-{sport.upper()}-{digest[:20].upper()}",
        "sport": sport,
        "source": source,
        "rows": int(len(frame)),
        "distinct_dates": int(dates.nunique()),
        "cutoff_time": None if pd.isna(cutoff) else cutoff.isoformat(),
        "dataset_sha256": digest,
    }


def _partition_by_date(dates: Iterable[Any], *, limits: ChallengerFactoryLimits) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    parsed = pd.to_datetime(pd.Series(list(dates)), utc=True, errors="coerce")
    if parsed.isna().any():
        return None
    groups = pd.Index(sorted(parsed.unique()))
    if len(groups) < limits.minimum_distinct_dates:
        return None
    holdout_groups = max(2, int(np.ceil(len(groups) * limits.holdout_fraction)))
    calibration_groups = max(2, int(np.ceil(len(groups) * limits.calibration_fraction)))
    train_groups = len(groups) - holdout_groups - calibration_groups
    if train_groups < 4:
        return None
    train_end = groups[train_groups - 1]
    calibration_end = groups[train_groups + calibration_groups - 1]
    values = parsed.to_numpy()
    train = np.flatnonzero(values <= train_end)
    calibration = np.flatnonzero((values > train_end) & (values <= calibration_end))
    holdout = np.flatnonzero(values > calibration_end)
    if min(len(train), len(calibration), len(holdout)) < 2:
        return None
    return train, calibration, holdout


def _portable_logistic(model: LogisticRegression, scaler: StandardScaler, *, features: tuple[str, ...], temperature: float) -> dict[str, Any]:
    return {
        "format": "portable_logistic_v1",
        "features": list(features),
        "scaler_mean": scaler.mean_.astype(float).tolist(),
        "scaler_scale": scaler.scale_.astype(float).tolist(),
        "coef": model.coef_.astype(float).tolist(),
        "intercept": model.intercept_.astype(float).tolist(),
        "classes": [int(value) for value in model.classes_],
        "temperature": float(temperature),
    }


def _football_elo_baseline(elo_home_probability: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(elo_home_probability, dtype=float), 0.02, 0.98)
    draw = 0.20 + 0.12 * (1.0 - np.abs(2.0 * p - 1.0))
    remaining = 1.0 - draw
    home = remaining * p
    away = remaining * (1.0 - p)
    result = np.column_stack([away, draw, home])
    return result / result.sum(axis=1, keepdims=True)


def _multiclass_metrics(target: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    probabilities = np.clip(np.asarray(probabilities, dtype=float), 1e-9, 1.0)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    return {
        "log_loss": float(log_loss(target, probabilities, labels=[0, 1, 2])),
        "brier": float(multiclass_brier(target, probabilities, n_classes=3)),
        "ece": float(expected_calibration_error(target, probabilities)),
        "accuracy": float(np.mean(np.argmax(probabilities, axis=1) == target)),
    }


def _binary_metrics(target: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    probabilities = np.clip(np.asarray(probabilities, dtype=float), 1e-9, 1 - 1e-9)
    return {
        "log_loss": float(log_loss(target, probabilities, labels=[0, 1])),
        "brier": float(binary_brier(target, probabilities)),
        "ece": float(expected_calibration_error(target, probabilities)),
        "accuracy": float(np.mean((probabilities >= 0.5).astype(int) == target)),
    }


def _status_from_metrics(
    *, challenger: dict[str, float], baseline: dict[str, float], limits: ChallengerFactoryLimits,
) -> tuple[str, str]:
    if challenger["log_loss"] <= baseline["log_loss"] - limits.log_loss_improvement_required and challenger["ece"] <= baseline["ece"] + limits.ece_tolerance:
        return "candidate", "challenger_passed_locked_holdout"
    return "hold", "challenger_did_not_pass_non_degradation_gates"


def train_football_challenger(frame: pd.DataFrame, *, limits: ChallengerFactoryLimits | None = None) -> dict[str, Any]:
    limits = limits or ChallengerFactoryLimits()
    snapshot = dataset_snapshot(frame, sport="football", source="local_football_archive")
    if len(frame) < limits.minimum_rows or snapshot["distinct_dates"] < limits.minimum_distinct_dates:
        return {
            "sport": "football", "status": "collecting", "reason": "insufficient_training_history",
            "dataset": snapshot, "minimum_rows": limits.minimum_rows,
            "minimum_distinct_dates": limits.minimum_distinct_dates, "provider_credits_consumed": 0,
        }
    features = FootballPredictor().build_features(frame)
    partitions = _partition_by_date(features["date"], limits=limits)
    if partitions is None:
        return {"sport": "football", "status": "collecting", "reason": "chronological_partition_unavailable", "dataset": snapshot, "provider_credits_consumed": 0}
    train, calibration, holdout = partitions
    X = features.loc[:, FOOTBALL_FEATURES].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    y = features["result_class"].astype(int).to_numpy()
    scaler = StandardScaler().fit(X[train])
    model = LogisticRegression(C=1.0, max_iter=800, solver="lbfgs", random_state=42)
    model.fit(scaler.transform(X[train]), y[train])
    calibration_raw = model.predict_proba(scaler.transform(X[calibration]))
    temperature = fit_temperature_multiclass(calibration_raw, y[calibration])
    holdout_probabilities = apply_temperature_multiclass(model.predict_proba(scaler.transform(X[holdout])), temperature)
    baseline_probabilities = _football_elo_baseline(features.iloc[holdout]["elo_home_prob"].to_numpy(dtype=float))
    challenger_metrics = _multiclass_metrics(y[holdout], holdout_probabilities)
    baseline_metrics = _multiclass_metrics(y[holdout], baseline_probabilities)
    status, reason = _status_from_metrics(challenger=challenger_metrics, baseline=baseline_metrics, limits=limits)
    parameters = _portable_logistic(model, scaler, features=FOOTBALL_FEATURES, temperature=temperature)
    digest = sha256(json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "sport": "football", "status": status, "reason": reason,
        "challenger_id": f"SCH-FOOTBALL-{digest[:16].upper()}",
        "model_type": "regularized_multinomial_logistic",
        "dataset": snapshot,
        "partitions": {"train": int(len(train)), "calibration": int(len(calibration)), "holdout": int(len(holdout))},
        "features": list(FOOTBALL_FEATURES),
        "baseline": {"name": "elo_three_way_baseline", "holdout": baseline_metrics},
        "challenger": {"holdout": challenger_metrics, "portable_parameters": parameters, "artifact_sha256": digest},
        "provider_credits_consumed": 0,
        "automatic_promotion": False,
    }


def _surface_breakdown(surface: pd.Series, target: np.ndarray, probabilities: np.ndarray, indices: np.ndarray) -> dict[str, Any]:
    result: dict[str, Any] = {}
    holdout_surface = surface.iloc[indices].fillna("unknown").astype(str).str.lower().to_numpy()
    for name in sorted(set(holdout_surface)):
        mask = holdout_surface == name
        if int(mask.sum()) < 2:
            result[name] = {"rows": int(mask.sum()), "status": "not_evaluable"}
        else:
            result[name] = {"rows": int(mask.sum()), **_binary_metrics(target[indices][mask], probabilities[mask])}
    return result


def train_tennis_challenger(frame: pd.DataFrame, *, limits: ChallengerFactoryLimits | None = None) -> dict[str, Any]:
    limits = limits or ChallengerFactoryLimits()
    snapshot = dataset_snapshot(frame, sport="tennis", source="local_tennis_archive")
    if len(frame) < limits.minimum_rows or snapshot["distinct_dates"] < limits.minimum_distinct_dates:
        return {
            "sport": "tennis", "status": "collecting", "reason": "insufficient_surface_aware_history",
            "dataset": snapshot, "minimum_rows": limits.minimum_rows,
            "minimum_distinct_dates": limits.minimum_distinct_dates,
            "surface_counts": frame.get("surface", pd.Series(dtype=str)).fillna("unknown").astype(str).str.lower().value_counts().to_dict(),
            "provider_credits_consumed": 0,
        }
    features = TennisPredictor().build_features(frame)
    partitions = _partition_by_date(features["date"], limits=limits)
    if partitions is None:
        return {"sport": "tennis", "status": "collecting", "reason": "chronological_partition_unavailable", "dataset": snapshot, "provider_credits_consumed": 0}
    train, calibration, holdout = partitions
    X = features.loc[:, TENNIS_FEATURES].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    y = features["player1_win"].astype(int).to_numpy()
    scaler = StandardScaler().fit(X[train])
    model = LogisticRegression(C=0.5, max_iter=800, solver="lbfgs", random_state=42)
    model.fit(scaler.transform(X[train]), y[train])
    calibration_raw = model.predict_proba(scaler.transform(X[calibration]))[:, 1]
    temperature = fit_temperature_binary(calibration_raw, y[calibration])
    holdout_probabilities = apply_temperature_binary(model.predict_proba(scaler.transform(X[holdout]))[:, 1], temperature)
    baseline_probabilities = features.iloc[holdout]["elo_probability"].to_numpy(dtype=float)
    challenger_metrics = _binary_metrics(y[holdout], holdout_probabilities)
    baseline_metrics = _binary_metrics(y[holdout], baseline_probabilities)
    status, reason = _status_from_metrics(challenger=challenger_metrics, baseline=baseline_metrics, limits=limits)
    parameters = _portable_logistic(model, scaler, features=TENNIS_FEATURES, temperature=temperature)
    digest = sha256(json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "sport": "tennis", "status": status, "reason": reason,
        "challenger_id": f"SCH-TENNIS-{digest[:16].upper()}",
        "model_type": "surface_aware_regularized_logistic",
        "dataset": snapshot,
        "partitions": {"train": int(len(train)), "calibration": int(len(calibration)), "holdout": int(len(holdout))},
        "features": list(TENNIS_FEATURES),
        "baseline": {"name": "surface_elo_baseline", "holdout": baseline_metrics},
        "challenger": {"holdout": challenger_metrics, "portable_parameters": parameters, "artifact_sha256": digest},
        "surface_holdout": _surface_breakdown(features["surface"], y, holdout_probabilities, holdout),
        "provider_credits_consumed": 0,
        "automatic_promotion": False,
    }


def build_challenger_factory_report(
    *, root: Path, limits: ChallengerFactoryLimits | None = None,
    football_path: Path | None = None, tennis_path: Path | None = None,
) -> dict[str, Any]:
    limits = limits or ChallengerFactoryLimits()
    football_path = football_path or root / "data" / "real" / "football_epl_2021_2026.csv"
    tennis_path = tennis_path or root / "data" / "real_snapshot" / "tennis_atp_2025_snapshot.csv"
    football = train_football_challenger(pd.read_csv(football_path), limits=limits)
    tennis = train_tennis_challenger(pd.read_csv(tennis_path), limits=limits)
    candidates = sum(item.get("status") == "candidate" for item in (football, tennis))
    collecting = sum(item.get("status") == "collecting" for item in (football, tennis))
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting" if collecting else ("review_required" if candidates else "hold"),
        "sports": {"football": football, "tennis": tennis},
        "limits": {**asdict(limits), "provider_credits_consumed": 0, "automatic_promotion": False, "optimise_on_in_sample_roi": False},
        "next_action": (
            "Collect a broader multi-surface tennis archive before training the tennis challenger."
            if tennis.get("status") == "collecting"
            else "Review sport challengers; promotion remains manual and separate by sport."
        ),
    }
