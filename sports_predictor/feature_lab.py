from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from .common import (
    apply_temperature_binary,
    apply_temperature_multiclass,
    binary_brier,
    expected_calibration_error,
    fit_temperature_binary,
    fit_temperature_multiclass,
    multiclass_brier,
)


@dataclass(frozen=True)
class ExperimentSpec:
    """Pre-registered, bounded model research experiment."""

    sport: str
    hypothesis: str
    feature_set: tuple[str, ...]
    primary_metric: str = "log_loss"
    maximum_candidates: int = 4
    minimum_events: int = 30
    holdout_fraction: float = 0.20

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["feature_set"] = list(self.feature_set)
        payload["experiment_id"] = experiment_identifier(self)
        return payload


def experiment_identifier(spec: ExperimentSpec) -> str:
    payload = {
        "sport": spec.sport,
        "hypothesis": spec.hypothesis,
        "feature_set": list(spec.feature_set),
        "primary_metric": spec.primary_metric,
        "maximum_candidates": int(spec.maximum_candidates),
        "minimum_events": int(spec.minimum_events),
        "holdout_fraction": float(spec.holdout_fraction),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()
    return f"EXP-{digest[:20]}"


def validate_feature_lineage(
    manifest: Iterable[Mapping[str, Any]], *, prediction_created_at: Any,
) -> dict[str, Any]:
    """Reject features that were unavailable when the prediction was frozen."""

    prediction_time = pd.to_datetime(prediction_created_at, utc=True, errors="coerce")
    issues: list[dict[str, Any]] = []
    valid = 0
    total = 0
    for raw in manifest:
        total += 1
        name = str(raw.get("feature_name") or "unknown")
        available = pd.to_datetime(raw.get("available_at"), utc=True, errors="coerce")
        if pd.isna(prediction_time):
            issues.append({"feature": name, "reason": "prediction_time_invalid"})
            continue
        if pd.isna(available):
            issues.append({"feature": name, "reason": "available_at_missing"})
            continue
        if available > prediction_time:
            issues.append({
                "feature": name,
                "reason": "future_feature",
                "available_at": available.isoformat(),
                "prediction_created_at": prediction_time.isoformat(),
            })
            continue
        valid += 1
    return {
        "valid": not issues,
        "features_total": total,
        "features_valid": valid,
        "coverage": float(valid / total) if total else None,
        "issues": issues,
    }


def _settled_rows(rows: Iterable[Mapping[str, Any]], sport: str) -> list[Mapping[str, Any]]:
    filtered = [
        row for row in rows
        if str(row.get("status")) == "settled"
        and bool(row.get("temporal_valid", True))
        and str(row.get("sport")) == sport
    ]
    return sorted(
        filtered,
        key=lambda row: (
            str(row.get("commence_time") or ""),
            str(row.get("provider_event_id") or ""),
        ),
    )


def _football_arrays(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    probabilities: list[list[float]] = []
    targets: list[int] = []
    dates: list[str] = []
    target_map = {"away": 0, "draw": 1, "home": 2}
    for row in rows:
        probs = row.get("probabilities") or {}
        result = str((row.get("evaluation") or {}).get("result_class") or row.get("result_class") or "")
        try:
            vector = [float(probs["away"]), float(probs["draw"]), float(probs["home"])]
        except (KeyError, TypeError, ValueError):
            continue
        if result not in target_map or not np.isfinite(vector).all() or min(vector) <= 0:
            continue
        total = float(sum(vector))
        if total <= 0:
            continue
        probabilities.append([value / total for value in vector])
        targets.append(target_map[result])
        dates.append(str(row.get("commence_time") or ""))
    return np.asarray(probabilities, dtype=float), np.asarray(targets, dtype=int), dates


def _tennis_arrays(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    probabilities: list[float] = []
    targets: list[int] = []
    dates: list[str] = []
    for row in rows:
        probs = row.get("probabilities") or {}
        result = str((row.get("evaluation") or {}).get("result_class") or row.get("result_class") or "")
        try:
            p1 = float(probs["player_1"])
        except (KeyError, TypeError, ValueError):
            continue
        if result not in {"player_1", "player_2", "home", "away"} or not np.isfinite(p1) or not 0 < p1 < 1:
            continue
        probabilities.append(p1)
        targets.append(1 if result in {"player_1", "home"} else 0)
        dates.append(str(row.get("commence_time") or ""))
    return np.asarray(probabilities, dtype=float), np.asarray(targets, dtype=int), dates


def _chronological_calibration_holdout(
    dates: Sequence[str], *, minimum_calibration: int = 10, minimum_holdout: int = 8,
) -> tuple[slice, slice] | None:
    n = len(dates)
    if n < minimum_calibration + minimum_holdout:
        return None
    parsed = pd.to_datetime(pd.Series(list(dates)), utc=True, errors="coerce")
    if parsed.isna().any() or not parsed.is_monotonic_increasing:
        return None
    target = max(minimum_calibration, int(n * 0.70))
    target = min(target, n - minimum_holdout)
    # Never split an identical event timestamp group.
    while target < n and target > 0 and parsed.iloc[target] == parsed.iloc[target - 1]:
        target += 1
    if target > n - minimum_holdout:
        target = n - minimum_holdout
        while target > minimum_calibration and parsed.iloc[target] == parsed.iloc[target - 1]:
            target -= 1
    if target < minimum_calibration or n - target < minimum_holdout:
        return None
    return slice(0, target), slice(target, n)


def _multiclass_metrics(y: np.ndarray, probs: np.ndarray) -> dict[str, float]:
    return {
        "log_loss": float(log_loss(y, probs, labels=[0, 1, 2])),
        "brier": multiclass_brier(y, probs, 3),
        "ece": expected_calibration_error(y, probs),
    }


def _binary_metrics(y: np.ndarray, probs: np.ndarray) -> dict[str, float]:
    return {
        "log_loss": float(log_loss(y, probs, labels=[0, 1])),
        "brier": binary_brier(y, probs),
        "ece": expected_calibration_error(y, probs),
    }


def _reliability_label(*, events: int, status: str, metrics: Mapping[str, Any] | None) -> str:
    if events < 30 or status == "collecting":
        return "INSUFFICIENT_EVIDENCE"
    ece = float((metrics or {}).get("ece", 1.0))
    if status == "candidate" and events >= 100 and ece <= 0.08:
        return "HIGH_CONFIDENCE_RESEARCH"
    if status == "candidate" and events >= 60 and ece <= 0.12:
        return "MEDIUM_CONFIDENCE_RESEARCH"
    return "LOW_CONFIDENCE_RESEARCH"


def calibrate_sport(
    rows: Iterable[Mapping[str, Any]], *, sport: str, minimum_events: int = 30,
) -> dict[str, Any]:
    """Evaluate a bounded calibrator on an untouched chronological holdout."""

    settled = _settled_rows(rows, sport)
    if sport == "football":
        raw, target, dates = _football_arrays(settled)
    elif sport == "tennis":
        raw, target, dates = _tennis_arrays(settled)
    else:
        raise ValueError("sport must be football or tennis")

    events = int(len(target))
    if events < minimum_events:
        status = "collecting"
        return {
            "sport": sport,
            "status": status,
            "reason": "insufficient_settled_events",
            "events": events,
            "minimum_required": minimum_events,
            "selected_calibrator": "identity",
            "holdout": None,
            "reliability": _reliability_label(events=events, status=status, metrics=None),
            "provider_credits_consumed": 0,
        }

    split = _chronological_calibration_holdout(dates)
    if split is None:
        status = "collecting"
        return {
            "sport": sport,
            "status": status,
            "reason": "insufficient_distinct_chronological_groups",
            "events": events,
            "minimum_required": minimum_events,
            "selected_calibrator": "identity",
            "holdout": None,
            "reliability": _reliability_label(events=events, status=status, metrics=None),
            "provider_credits_consumed": 0,
        }
    calibration_slice, holdout_slice = split
    y_cal, y_hold = target[calibration_slice], target[holdout_slice]
    candidates: list[dict[str, Any]] = []

    if sport == "football":
        p_cal, p_hold = raw[calibration_slice], raw[holdout_slice]
        candidates.append({
            "name": "identity",
            "parameters": {},
            "holdout_probabilities": p_hold,
            "calibration_metrics": _multiclass_metrics(y_cal, p_cal),
        })
        temperature = fit_temperature_multiclass(p_cal, y_cal)
        calibrated_cal = apply_temperature_multiclass(p_cal, temperature)
        calibrated_hold = apply_temperature_multiclass(p_hold, temperature)
        candidates.append({
            "name": "temperature_multiclass",
            "parameters": {"temperature": float(temperature)},
            "holdout_probabilities": calibrated_hold,
            "calibration_metrics": _multiclass_metrics(y_cal, calibrated_cal),
        })
        metric_fn = _multiclass_metrics
    else:
        p_cal, p_hold = raw[calibration_slice], raw[holdout_slice]
        candidates.append({
            "name": "identity",
            "parameters": {},
            "holdout_probabilities": p_hold,
            "calibration_metrics": _binary_metrics(y_cal, p_cal),
        })
        temperature = fit_temperature_binary(p_cal, y_cal)
        candidates.append({
            "name": "temperature_binary",
            "parameters": {"temperature": float(temperature)},
            "holdout_probabilities": apply_temperature_binary(p_hold, temperature),
            "calibration_metrics": _binary_metrics(y_cal, apply_temperature_binary(p_cal, temperature)),
        })
        logits_cal = np.log(np.clip(p_cal, 1e-9, 1 - 1e-9) / np.clip(1 - p_cal, 1e-9, 1))
        logits_hold = np.log(np.clip(p_hold, 1e-9, 1 - 1e-9) / np.clip(1 - p_hold, 1e-9, 1))
        if len(np.unique(y_cal)) == 2:
            model = LogisticRegression(C=1.0, solver="lbfgs", random_state=42)
            model.fit(logits_cal.reshape(-1, 1), y_cal)
            platt_cal = model.predict_proba(logits_cal.reshape(-1, 1))[:, 1]
            platt_hold = model.predict_proba(logits_hold.reshape(-1, 1))[:, 1]
            candidates.append({
                "name": "platt_logit",
                "parameters": {
                    "coef": float(model.coef_[0][0]),
                    "intercept": float(model.intercept_[0]),
                },
                "holdout_probabilities": platt_hold,
                "calibration_metrics": _binary_metrics(y_cal, platt_cal),
            })
        metric_fn = _binary_metrics

    for candidate in candidates:
        candidate["holdout_metrics"] = metric_fn(y_hold, candidate.pop("holdout_probabilities"))
    candidates.sort(
        key=lambda item: (
            float(item["calibration_metrics"]["log_loss"]),
            float(item["calibration_metrics"]["ece"]),
        )
    )
    chosen = candidates[0]
    identity = next(item for item in candidates if item["name"] == "identity")
    selected = chosen
    # The calibration window chooses the candidate, but the untouched holdout
    # can veto it. A slightly worse log loss or materially worse ECE means the
    # identity mapping remains champion.
    if (
        float(chosen["holdout_metrics"]["log_loss"]) > float(identity["holdout_metrics"]["log_loss"]) + 0.002
        or float(chosen["holdout_metrics"]["ece"]) > float(identity["holdout_metrics"]["ece"]) + 0.015
    ):
        selected = identity
        status = "hold"
        reason = "calibrator_failed_holdout_non_degradation"
    elif chosen["name"] == "identity":
        status = "hold"
        reason = "no_calibrator_improved_calibration_window"
    else:
        status = "candidate"
        reason = "calibrator_passed_chronological_holdout"

    holdout_metrics = selected["holdout_metrics"]
    return {
        "sport": sport,
        "status": status,
        "reason": reason,
        "events": events,
        "calibration_events": int(calibration_slice.stop - calibration_slice.start),
        "holdout_events": int(holdout_slice.stop - holdout_slice.start),
        "selected_calibrator": selected["name"],
        "parameters": selected["parameters"],
        "holdout": holdout_metrics,
        "identity_holdout": identity["holdout_metrics"],
        "candidates": [
            {
                "name": item["name"],
                "parameters": item["parameters"],
                "calibration_metrics": item["calibration_metrics"],
                "holdout_metrics": item["holdout_metrics"],
            }
            for item in candidates
        ],
        "reliability": _reliability_label(events=events, status=status, metrics=holdout_metrics),
        "provider_credits_consumed": 0,
    }


def audit_feature_lineage(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    manifests = 0
    checked_features = 0
    future_violations: list[dict[str, Any]] = []
    missing_manifests = 0
    for row in rows:
        fixture = row.get("fixture") or {}
        manifest = fixture.get("feature_manifest")
        if not isinstance(manifest, list) or not manifest:
            missing_manifests += 1
            continue
        manifests += 1
        audit = validate_feature_lineage(
            manifest, prediction_created_at=row.get("prediction_created_at"),
        )
        checked_features += int(audit["features_total"])
        for issue in audit["issues"]:
            if issue.get("reason") == "future_feature":
                future_violations.append({
                    "provider_event_id": row.get("provider_event_id"),
                    **issue,
                })
    return {
        "valid": not future_violations,
        "manifests_present": manifests,
        "rows_without_manifest": missing_manifests,
        "features_checked": checked_features,
        "future_feature_violations": future_violations,
        "mode": "legacy_rows_allowed_but_new_experiments_require_manifest",
    }


def _default_experiments() -> list[ExperimentSpec]:
    return [
        ExperimentSpec(
            sport="football",
            hypothesis="Recent strength, home/away context and rest improve probability calibration across chronological folds.",
            feature_set=(
                "elo_diff", "attack_form", "defence_form", "home_away_context",
                "rest_days", "matches_seen", "season_phase", "cold_start",
            ),
        ),
        ExperimentSpec(
            sport="tennis",
            hypothesis="Surface-specific Elo, ranking, form and rest improve tennis calibration without relying on future information.",
            feature_set=(
                "global_elo", "surface_elo", "ranking", "ranking_points", "recent_form",
                "rest_days", "tournament_level", "best_of", "cold_start",
            ),
        ),
    ]


def build_feature_lab_report(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    football = calibrate_sport(rows, sport="football")
    tennis = calibrate_sport(rows, sport="tennis")
    experiments = []
    for spec, calibration in zip(_default_experiments(), (football, tennis)):
        if calibration["events"] < spec.minimum_events:
            experiment_status = "planned"
        elif calibration["status"] == "candidate":
            experiment_status = "approved_for_challenger"
        else:
            experiment_status = "rejected"
        experiments.append({**spec.to_dict(), "status": experiment_status})

    levels = {football["reliability"], tennis["reliability"]}
    if levels == {"HIGH_CONFIDENCE_RESEARCH"}:
        overall = "high"
    elif "INSUFFICIENT_EVIDENCE" in levels:
        overall = "collecting"
    elif "LOW_CONFIDENCE_RESEARCH" in levels:
        overall = "low"
    else:
        overall = "medium"
    lineage = audit_feature_lineage(rows)
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if overall != "collecting" and lineage["valid"] else "collecting",
        "overall_reliability": overall,
        "sports": {"football": football, "tennis": tennis},
        "experiments": experiments,
        "feature_lineage": lineage,
        "limits": {
            "maximum_experiments_per_sport": 12,
            "maximum_calibrators_per_sport": 4,
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
            "optimise_models_on_in_sample_roi": False,
        },
        "next_action": (
            "Continue collecting temporally valid settled events."
            if overall == "collecting"
            else "Review calibration candidates in expert mode; promotion remains manual."
        ),
    }
