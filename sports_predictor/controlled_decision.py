from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from .challenger_factory import (
    ChallengerFactoryLimits,
    _football_elo_baseline,
    _multiclass_metrics,
    dataset_snapshot,
)
from .common import apply_temperature_multiclass, fit_temperature_multiclass
from .evidence_acceleration import (
    TennisReadinessLimits,
    build_tennis_dataset_package,
    normalise_tennis_import,
)
from .football import FootballPredictor


@dataclass(frozen=True)
class ControlledDecisionLimits:
    maximum_football_challengers: int = 2
    poisson_alphas: tuple[float, ...] = (0.05, 0.20, 1.0)
    hybrid_weights: tuple[float, ...] = (0.25, 0.50, 0.75)
    consulted_holdout_fraction: float = 0.20
    development_calibration_fraction: float = 0.15
    development_validation_fraction: float = 0.15
    minimum_new_holdout_dates: int = 30
    log_loss_improvement_required: float = 0.002
    ece_tolerance: float = 0.015
    subgroup_log_loss_tolerance: float = 0.020
    minimum_subgroup_rows: int = 10


POISSON_FEATURES = (
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
    "elo_diff",
)


def _portable_poisson(model: PoissonRegressor, scaler: StandardScaler) -> dict[str, Any]:
    return {
        "coef": model.coef_.astype(float).tolist(),
        "intercept": float(model.intercept_),
        "scaler_mean": scaler.mean_.astype(float).tolist(),
        "scaler_scale": scaler.scale_.astype(float).tolist(),
        "alpha": float(model.alpha),
    }


def _development_partitions(dates: pd.Series, limits: ControlledDecisionLimits) -> dict[str, Any] | None:
    parsed = pd.to_datetime(dates, utc=True, errors="coerce")
    if parsed.isna().any():
        return None
    groups = pd.Index(sorted(parsed.unique()))
    if len(groups) < 30:
        return None
    consulted_count = max(2, int(np.ceil(len(groups) * limits.consulted_holdout_fraction)))
    development_groups = groups[:-consulted_count]
    if len(development_groups) < 12:
        return None
    validation_count = max(2, int(np.ceil(len(development_groups) * limits.development_validation_fraction)))
    calibration_count = max(2, int(np.ceil(len(development_groups) * limits.development_calibration_fraction)))
    train_count = len(development_groups) - validation_count - calibration_count
    if train_count < 6:
        return None
    train_end = development_groups[train_count - 1]
    calibration_end = development_groups[train_count + calibration_count - 1]
    development_end = development_groups[-1]
    values = parsed.to_numpy()
    return {
        "train": np.flatnonzero(values <= train_end),
        "calibration": np.flatnonzero((values > train_end) & (values <= calibration_end)),
        "validation": np.flatnonzero((values > calibration_end) & (values <= development_end)),
        "consulted_holdout": np.flatnonzero(values > development_end),
        "boundaries": {
            "train_end": pd.Timestamp(train_end).isoformat(),
            "calibration_end": pd.Timestamp(calibration_end).isoformat(),
            "development_validation_end": pd.Timestamp(development_end).isoformat(),
            "consulted_holdout_start": pd.Timestamp(groups[-consulted_count]).isoformat(),
            "consulted_holdout_end": pd.Timestamp(groups[-1]).isoformat(),
        },
    }


def _poisson_probabilities(home: np.ndarray, away: np.ndarray, rho: float) -> np.ndarray:
    predictor = FootballPredictor()
    return predictor._poisson_probs(np.clip(home, 0.08, 5.5), np.clip(away, 0.08, 5.5), rho)


def _fit_poisson_models(
    features: pd.DataFrame,
    train: np.ndarray,
    calibration: np.ndarray,
    limits: ControlledDecisionLimits,
) -> dict[str, Any]:
    X = features.loc[:, POISSON_FEATURES].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    home_goals = features["home_goals"].astype(float).to_numpy()
    away_goals = features["away_goals"].astype(float).to_numpy()
    y = features["result_class"].astype(int).to_numpy()
    scaler = StandardScaler().fit(X[train])
    best: dict[str, Any] | None = None
    for alpha in limits.poisson_alphas:
        home_model = PoissonRegressor(alpha=float(alpha), max_iter=600)
        away_model = PoissonRegressor(alpha=float(alpha), max_iter=600)
        home_model.fit(scaler.transform(X[train]), home_goals[train])
        away_model.fit(scaler.transform(X[train]), away_goals[train])
        home_cal = home_model.predict(scaler.transform(X[calibration]))
        away_cal = away_model.predict(scaler.transform(X[calibration]))
        rho = FootballPredictor()._fit_rho(
            np.clip(home_cal, 0.08, 5.5),
            np.clip(away_cal, 0.08, 5.5),
            home_goals[calibration],
            away_goals[calibration],
        )
        raw = _poisson_probabilities(home_cal, away_cal, rho)
        loss = float(log_loss(y[calibration], raw, labels=[0, 1, 2]))
        candidate = {
            "alpha": float(alpha),
            "home_model": home_model,
            "away_model": away_model,
            "scaler": scaler,
            "rho": float(rho),
            "calibration_raw": raw,
            "calibration_log_loss": loss,
        }
        if best is None or loss < best["calibration_log_loss"]:
            best = candidate
    assert best is not None
    return {**best, "X": X, "target": y}


def _subgroup_veto(
    features: pd.DataFrame,
    indices: np.ndarray,
    target: np.ndarray,
    challenger: np.ndarray,
    baseline: np.ndarray,
    limits: ControlledDecisionLimits,
) -> dict[str, Any]:
    hold = features.iloc[indices].reset_index(drop=True)
    outcomes = np.asarray(["away", "draw", "home"], dtype=object)[target]
    rest_gap = np.abs(hold["home_rest_days"].to_numpy(dtype=float) - hold["away_rest_days"].to_numpy(dtype=float))
    rest_context = np.where(rest_gap >= 4, "rest_imbalance", "similar_rest")
    checks: dict[str, Any] = {}
    vetoes: list[str] = []
    for dimension, labels, watched in (
        ("outcome", outcomes, {"away", "draw"}),
        ("rest_context", rest_context, {"rest_imbalance"}),
    ):
        values = np.asarray(labels, dtype=object)
        groups: dict[str, Any] = {}
        for label in sorted(set(values)):
            mask = values == label
            rows = int(mask.sum())
            if rows < limits.minimum_subgroup_rows:
                groups[str(label)] = {"rows": rows, "status": "not_evaluable"}
                continue
            challenger_metrics = _multiclass_metrics(target[mask], challenger[mask])
            baseline_metrics = _multiclass_metrics(target[mask], baseline[mask])
            delta = float(challenger_metrics["log_loss"] - baseline_metrics["log_loss"])
            passed = delta <= limits.subgroup_log_loss_tolerance
            groups[str(label)] = {
                "rows": rows,
                "status": "evaluated",
                "delta_log_loss": delta,
                "passed": passed,
            }
            if label in watched and not passed:
                vetoes.append(f"{dimension}:{label}")
        checks[dimension] = groups
    return {"passed": not vetoes, "vetoes": vetoes, "groups": checks}


def _decision_status(
    challenger: dict[str, float],
    baseline: dict[str, float],
    subgroup: dict[str, Any],
    limits: ControlledDecisionLimits,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if challenger["log_loss"] > baseline["log_loss"] - limits.log_loss_improvement_required:
        reasons.append("development_log_loss_gate_failed")
    if challenger["ece"] > baseline["ece"] + limits.ece_tolerance:
        reasons.append("development_ece_gate_failed")
    if not subgroup["passed"]:
        reasons.append("protected_subgroup_veto")
    return ("development_candidate" if not reasons else "hold"), reasons


def build_bounded_football_round(
    frame: pd.DataFrame,
    *,
    limits: ControlledDecisionLimits | None = None,
) -> dict[str, Any]:
    limits = limits or ControlledDecisionLimits()
    features = FootballPredictor().build_features(frame)
    snapshot = dataset_snapshot(frame, sport="football", source="local_football_archive")
    partitions = _development_partitions(features["date"], limits)
    if partitions is None:
        return {
            "status": "collecting",
            "reason": "development_partition_unavailable",
            "dataset": snapshot,
            "challengers": [],
            "provider_credits_consumed": 0,
        }
    train = partitions["train"]
    calibration = partitions["calibration"]
    validation = partitions["validation"]
    fitted = _fit_poisson_models(features, train, calibration, limits)
    X = fitted["X"]
    y = fitted["target"]
    home_validation = fitted["home_model"].predict(fitted["scaler"].transform(X[validation]))
    away_validation = fitted["away_model"].predict(fitted["scaler"].transform(X[validation]))
    poisson_raw_validation = _poisson_probabilities(home_validation, away_validation, fitted["rho"])
    temperature = fit_temperature_multiclass(fitted["calibration_raw"], y[calibration])
    poisson_validation = apply_temperature_multiclass(poisson_raw_validation, temperature)
    baseline_validation = _football_elo_baseline(features.iloc[validation]["elo_home_prob"].to_numpy(dtype=float))
    poisson_metrics = _multiclass_metrics(y[validation], poisson_validation)
    baseline_metrics = _multiclass_metrics(y[validation], baseline_validation)
    poisson_subgroup = _subgroup_veto(features, validation, y[validation], poisson_validation, baseline_validation, limits)
    poisson_status, poisson_reasons = _decision_status(poisson_metrics, baseline_metrics, poisson_subgroup, limits)
    poisson_parameters = {
        "format": "portable_regularized_poisson_v1",
        "features": list(POISSON_FEATURES),
        "home": _portable_poisson(fitted["home_model"], fitted["scaler"]),
        "away": _portable_poisson(fitted["away_model"], fitted["scaler"]),
        "rho": fitted["rho"],
        "temperature": float(temperature),
    }
    poisson_hash = sha256(json.dumps(poisson_parameters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    baseline_calibration = _football_elo_baseline(features.iloc[calibration]["elo_home_prob"].to_numpy(dtype=float))
    best_weight = None
    best_loss = float("inf")
    for weight in limits.hybrid_weights:
        blended = float(weight) * fitted["calibration_raw"] + (1.0 - float(weight)) * baseline_calibration
        loss = float(log_loss(y[calibration], blended, labels=[0, 1, 2]))
        if loss < best_loss:
            best_loss = loss
            best_weight = float(weight)
    assert best_weight is not None
    hybrid_calibration_raw = best_weight * fitted["calibration_raw"] + (1.0 - best_weight) * baseline_calibration
    hybrid_temperature = fit_temperature_multiclass(hybrid_calibration_raw, y[calibration])
    hybrid_validation_raw = best_weight * poisson_raw_validation + (1.0 - best_weight) * baseline_validation
    hybrid_validation = apply_temperature_multiclass(hybrid_validation_raw, hybrid_temperature)
    hybrid_metrics = _multiclass_metrics(y[validation], hybrid_validation)
    hybrid_subgroup = _subgroup_veto(features, validation, y[validation], hybrid_validation, baseline_validation, limits)
    hybrid_status, hybrid_reasons = _decision_status(hybrid_metrics, baseline_metrics, hybrid_subgroup, limits)
    hybrid_parameters = {
        "format": "portable_poisson_elo_hybrid_v1",
        "poisson_artifact_sha256": poisson_hash,
        "poisson_weight": best_weight,
        "elo_weight": 1.0 - best_weight,
        "temperature": float(hybrid_temperature),
    }
    hybrid_hash = sha256(json.dumps(hybrid_parameters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    challengers = [
        {
            "experiment_id": f"EXP-FOOTBALL-{poisson_hash[:20].upper()}",
            "model_type": "regularized_poisson_attack_defence",
            "status": poisson_status,
            "decision_reasons": poisson_reasons or ["development_gates_passed_future_holdout_required"],
            "development_validation": poisson_metrics,
            "baseline_validation": baseline_metrics,
            "subgroup_gates": poisson_subgroup,
            "portable_parameters": poisson_parameters,
            "artifact_sha256": poisson_hash,
        },
        {
            "experiment_id": f"EXP-FOOTBALL-{hybrid_hash[:20].upper()}",
            "model_type": "hybrid_poisson_elo",
            "status": hybrid_status,
            "decision_reasons": hybrid_reasons or ["development_gates_passed_future_holdout_required"],
            "development_validation": hybrid_metrics,
            "baseline_validation": baseline_metrics,
            "subgroup_gates": hybrid_subgroup,
            "portable_parameters": hybrid_parameters,
            "artifact_sha256": hybrid_hash,
        },
    ]
    candidates = [item for item in challengers if item["status"] == "development_candidate"]
    best = min(challengers, key=lambda item: item["development_validation"]["log_loss"])
    cutoff = snapshot.get("cutoff_time")
    generation_payload = f"{snapshot['dataset_id']}:2:{cutoff}:future".encode("utf-8")
    promotion_generation = {
        "generation_id": f"HG-FOOTBALL-{sha256(generation_payload).hexdigest()[:20].upper()}",
        "generation": 2,
        "dataset_id": snapshot["dataset_id"],
        "sport": "football",
        "status": "open_collecting",
        "start_after": cutoff,
        "required_new_distinct_dates": limits.minimum_new_holdout_dates,
        "current_new_distinct_dates": 0,
        "consulted": False,
        "retuning_after_consultation_allowed": False,
    }
    consulted = {
        "generation_id": f"HG-FOOTBALL-{sha256((snapshot['dataset_id'] + ':1:consulted').encode()).hexdigest()[:20].upper()}",
        "generation": 1,
        "dataset_id": snapshot["dataset_id"],
        "sport": "football",
        "status": "consulted_diagnostic_only",
        "consulted": True,
        "consulted_at": datetime.now(timezone.utc).isoformat(),
        **partitions["boundaries"],
        "retuning_after_consultation_allowed": False,
    }
    return {
        "status": "development_review" if candidates else "hold",
        "reason": "future_promotion_holdout_required" if candidates else "no_development_challenger_passed",
        "dataset": snapshot,
        "partitions": {key: int(len(partitions[key])) for key in ("train", "calibration", "validation", "consulted_holdout")},
        "consulted_holdout_generation": consulted,
        "promotion_holdout_generation": promotion_generation,
        "baseline": {"name": "elo_three_way_baseline", "development_validation": baseline_metrics},
        "challengers": challengers[: limits.maximum_football_challengers],
        "best_development_challenger": best["experiment_id"],
        "promotion_ready": False,
        "provider_credits_consumed": 0,
        "automatic_promotion": False,
    }


def _match_key(frame: pd.DataFrame) -> pd.Series:
    left = frame["winner_name"].astype(str)
    right = frame["loser_name"].astype(str)
    first = np.where(left <= right, left, right)
    second = np.where(left <= right, right, left)
    dates = pd.to_datetime(frame["date"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
    return dates.fillna("invalid") + "|" + frame["tournament"].astype(str) + "|" + pd.Series(first, index=frame.index) + "|" + pd.Series(second, index=frame.index)


def build_incremental_tennis_package(
    previous: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    source: str,
    license_status: str,
    previous_dataset_id: str,
    limits: TennisReadinessLimits | None = None,
) -> dict[str, Any]:
    previous_accepted, previous_quarantined, previous_quality = normalise_tennis_import(previous)
    incoming_accepted, incoming_quarantined, incoming_quality = normalise_tennis_import(incoming)
    previous_accepted = previous_accepted.copy()
    incoming_accepted = incoming_accepted.copy()
    previous_accepted["_match_key"] = _match_key(previous_accepted)
    incoming_accepted["_match_key"] = _match_key(incoming_accepted)

    previous_by_key = dict(zip(previous_accepted["_match_key"].astype(str), previous_accepted["row_sha256"].astype(str)))
    incoming_by_key = dict(zip(incoming_accepted["_match_key"].astype(str), incoming_accepted["row_sha256"].astype(str)))
    corrections = sorted(key for key in set(previous_by_key) & set(incoming_by_key) if previous_by_key[key] != incoming_by_key[key])
    unchanged = sorted(key for key in set(previous_by_key) & set(incoming_by_key) if previous_by_key[key] == incoming_by_key[key])

    retained = previous_accepted.loc[~previous_accepted["_match_key"].isin(corrections)].drop(columns=["_match_key"])
    additions = incoming_accepted.loc[~incoming_accepted["_match_key"].isin(unchanged)].drop(columns=["_match_key"])
    merged = pd.concat([retained, additions], ignore_index=True, sort=False)
    package = build_tennis_dataset_package(
        merged,
        source=source,
        license_status=license_status,
        supersedes_dataset_id=previous_dataset_id,
        limits=limits,
    )
    quarantine = pd.concat([previous_quarantined, incoming_quarantined], ignore_index=True, sort=False)
    package["quarantined"] = quarantine
    package["catalog"]["quality"]["incremental_quarantined_rows"] = int(len(incoming_quarantined))
    package["catalog"]["quality"]["result_corrections"] = int(len(corrections))
    package["incremental"] = {
        "previous_dataset_id": previous_dataset_id,
        "previous_accepted_rows": int(len(previous_accepted)),
        "incoming_raw_rows": int(len(incoming)),
        "incoming_accepted_rows": int(len(incoming_accepted)),
        "new_rows": int(len(additions) - len(corrections)),
        "unchanged_duplicates": int(len(unchanged)),
        "result_corrections": int(len(corrections)),
        "correction_match_keys": corrections[:50],
        "merged_rows": int(len(package["accepted"])),
        "incoming_quality": incoming_quality,
        "previous_quality": previous_quality,
        "provider_credits_consumed": 0,
    }
    return package


def _validate_long_session(path: Path, *, expected_version: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_run", "path": str(path), "passed": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid_report", "path": str(path), "passed": False, "error": type(exc).__name__}
    problems: list[str] = []
    if payload.get("status") != "ok":
        problems.append("status_not_ok")
    if payload.get("expected_version") not in {expected_version, None}:
        problems.append("version_mismatch")
    if payload.get("console_errors"):
        problems.append("console_errors")
    if payload.get("page_errors"):
        problems.append("page_errors")
    if payload.get("one_compact_panel_at_a_time") is False:
        problems.append("multiple_active_panels")
    if int(payload.get("dom_growth") or 0) > 80:
        problems.append("dom_growth_exceeded")
    return {"status": "passed" if not problems else "failed", "passed": not problems, "problems": problems, "report": payload}


def build_controlled_model_decision_report(
    *,
    root: Path,
    football_path: Path | None = None,
    tennis_path: Path | None = None,
    app_version: str = "4.9.0",
) -> dict[str, Any]:
    football_path = football_path or root / "data" / "real" / "football_epl_2021_2026.csv"
    tennis_path = tennis_path or root / "data" / "real_snapshot" / "tennis_atp_2025_snapshot.csv"
    football = build_bounded_football_round(pd.read_csv(football_path))
    tennis_package = build_tennis_dataset_package(
        pd.read_csv(tennis_path),
        source="local_tennis_archive",
        license_status="research_only",
    )
    simple_validation = _validate_long_session(root / "artifacts" / "public_long_session_v4_9_simple.json", expected_version=app_version)
    expert_validation = _validate_long_session(root / "artifacts" / "public_long_session_v4_9_expert.json", expected_version=app_version)
    production_passed = simple_validation["passed"] and expert_validation["passed"]
    readiness = tennis_package["catalog"]["readiness"]
    status = "review_required" if (
        football.get("status") == "development_review"
        and production_passed
        and readiness.get("challenger_ready")
    ) else ("hold" if football.get("status") == "hold" else "collecting")
    decision_payload = {
        "football_dataset": football.get("dataset", {}).get("dataset_sha256"),
        "football_challengers": [item.get("artifact_sha256") for item in football.get("challengers", [])],
        "tennis_dataset": tennis_package["catalog"].get("dataset_sha256"),
        "production_simple": simple_validation.get("status"),
        "production_expert": expert_validation.get("status"),
    }
    decision_hash = sha256(json.dumps(decision_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision_id": f"CMD-{decision_hash[:20].upper()}",
        "status": status,
        "football": football,
        "tennis": {
            "catalog": tennis_package["catalog"],
            "holdout_generation": tennis_package["holdout_generation"],
            "progress": {
                "exploratory_rows": {"actual": readiness["rows"], "required": 500},
                "exploratory_dates": {"actual": readiness["distinct_dates"], "required": 50},
                "challenger_rows": {"actual": readiness["rows"], "required": 1500},
                "challenger_dates": {"actual": readiness["distinct_dates"], "required": 150},
            },
            "training_status": "blocked_below_readiness_gates" if not readiness["exploratory_ready"] else "exploratory_allowed",
        },
        "production_validation": {
            "status": "passed" if production_passed else "not_proven",
            "simple": simple_validation,
            "expert": expert_validation,
        },
        "limits": {
            **asdict(ControlledDecisionLimits()),
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
            "optimise_on_in_sample_roi": False,
            "new_simple_ui_tabs": 0,
        },
        "next_action": (
            "Run both public long-session scenarios and continue collecting future football and tennis evidence."
            if not production_passed
            else "Continue tennis collection and wait for a fresh sealed football promotion holdout."
        ),
    }
