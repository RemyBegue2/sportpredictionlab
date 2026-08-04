from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
import json
import re
import unicodedata

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from .challenger_factory import (
    ChallengerFactoryLimits,
    FOOTBALL_FEATURES,
    _football_elo_baseline,
    _multiclass_metrics,
    dataset_snapshot,
)
from .common import apply_temperature_multiclass, fit_temperature_multiclass
from .football import FootballPredictor


@dataclass(frozen=True)
class TennisReadinessLimits:
    exploratory_min_rows: int = 500
    exploratory_min_dates: int = 50
    challenger_min_rows: int = 1500
    challenger_min_dates: int = 150
    minimum_surface_rows_exploratory: int = 50
    minimum_surface_rows_challenger: int = 200
    minimum_distinct_surfaces: int = 2
    maximum_quarantine_fraction: float = 0.05


SURFACE_ALIASES = {
    "hard": "hard",
    "indoor hard": "hard",
    "outdoor hard": "hard",
    "dur": "hard",
    "clay": "clay",
    "terre": "clay",
    "terre battue": "clay",
    "grass": "grass",
    "gazon": "grass",
    "carpet": "carpet",
    "moquette": "carpet",
}

TENNIS_COLUMN_ALIASES = {
    "winner": "winner_name",
    "winnername": "winner_name",
    "w_name": "winner_name",
    "loser": "loser_name",
    "losername": "loser_name",
    "l_name": "loser_name",
    "tourney_date": "date",
    "match_date": "date",
    "tourney_name": "tournament",
    "tourney_level": "tournament_level",
    "winner_rank_points": "winner_rank_points",
    "loser_rank_points": "loser_rank_points",
    "w_rank": "winner_rank",
    "l_rank": "loser_rank",
    "w_pts": "winner_rank_points",
    "l_pts": "loser_rank_points",
}

CANONICAL_TENNIS_COLUMNS = (
    "date",
    "tour",
    "surface",
    "tournament_level",
    "tournament",
    "best_of",
    "winner_name",
    "loser_name",
    "winner_rank",
    "loser_rank",
    "winner_rank_points",
    "loser_rank_points",
    "winner_rank_available_at",
    "loser_rank_available_at",
    "source_row_id",
)


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _player_name(value: Any) -> str:
    return " ".join(part.capitalize() for part in _slug(value).split())


def _canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[str, str] = {}
    for column in frame.columns:
        normal = re.sub(r"[^a-z0-9]+", "_", str(column).strip().casefold()).strip("_")
        renamed[column] = TENNIS_COLUMN_ALIASES.get(normal, normal)
    result = frame.rename(columns=renamed).copy()
    for column in CANONICAL_TENNIS_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    return result


def _row_digest(row: pd.Series) -> str:
    payload = {
        key: None if pd.isna(row.get(key)) else str(row.get(key))
        for key in (
            "date",
            "tour",
            "surface",
            "tournament_level",
            "tournament",
            "best_of",
            "winner_name",
            "loser_name",
            "winner_rank",
            "loser_rank",
            "winner_rank_points",
            "loser_rank_points",
        )
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def normalise_tennis_import(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Normalise a tennis archive and quarantine rows that cannot be trusted.

    Ranking timestamps are optional for legacy imports. Missing timestamps are
    labelled ``legacy_unverified`` and keep the data readable, but they prevent
    a dataset from being approved for promotion-grade training.
    """
    raw_rows = int(len(frame))
    data = _canonical_columns(frame)
    data["date"] = pd.to_datetime(data["date"], utc=True, errors="coerce")
    data["winner_rank_available_at"] = pd.to_datetime(data["winner_rank_available_at"], utc=True, errors="coerce")
    data["loser_rank_available_at"] = pd.to_datetime(data["loser_rank_available_at"], utc=True, errors="coerce")
    data["winner_name"] = data["winner_name"].map(_player_name)
    data["loser_name"] = data["loser_name"].map(_player_name)
    data["surface"] = data["surface"].map(lambda value: SURFACE_ALIASES.get(_slug(value), "unknown"))
    data["tour"] = data["tour"].fillna("unknown").astype(str).str.upper().str.strip()
    data["tournament"] = data["tournament"].fillna("unknown").astype(str).str.strip()
    data["tournament_level"] = data["tournament_level"].fillna("unknown").astype(str).str.upper().str.strip()
    data["best_of"] = pd.to_numeric(data["best_of"], errors="coerce").fillna(3).clip(1, 5).astype(int)
    for column in ("winner_rank", "loser_rank", "winner_rank_points", "loser_rank_points"):
        data[column] = pd.to_numeric(data[column], errors="coerce")

    issue_lists: list[list[str]] = []
    lineage: list[str] = []
    for row in data.itertuples(index=False):
        issues: list[str] = []
        if pd.isna(row.date):
            issues.append("invalid_date")
        if not row.winner_name or not row.loser_name:
            issues.append("missing_player")
        if row.winner_name and row.winner_name == row.loser_name:
            issues.append("same_player")
        future = False
        for value_name, observed_name in (
            ("winner_rank", "winner_rank_available_at"),
            ("loser_rank", "loser_rank_available_at"),
        ):
            value = getattr(row, value_name)
            observed = getattr(row, observed_name)
            if not pd.isna(value) and not pd.isna(observed) and not pd.isna(row.date) and observed > row.date:
                issues.append("future_ranking")
                future = True
        if future:
            lineage.append("future_feature")
        else:
            rank_values_present = not pd.isna(row.winner_rank) or not pd.isna(row.loser_rank)
            timestamps_complete = not pd.isna(row.winner_rank_available_at) and not pd.isna(row.loser_rank_available_at)
            lineage.append("verified_pre_match" if (not rank_values_present or timestamps_complete) else "legacy_unverified")
        issue_lists.append(sorted(set(issues)))
    data["quality_issues"] = issue_lists
    data["lineage_status"] = lineage
    data["row_sha256"] = data.apply(_row_digest, axis=1)

    duplicate_mask = data.duplicated("row_sha256", keep="first")
    for index in data.index[duplicate_mask]:
        data.at[index, "quality_issues"] = sorted(set(data.at[index, "quality_issues"] + ["duplicate_row"]))

    quarantine_mask = data["quality_issues"].map(bool)
    accepted = data.loc[~quarantine_mask].copy()
    quarantined = data.loc[quarantine_mask].copy()
    accepted = accepted.sort_values(["date", "tournament", "winner_name", "loser_name"], kind="stable").reset_index(drop=True)
    quarantined = quarantined.reset_index(drop=True)
    issue_counts: dict[str, int] = {}
    for issues in quarantined["quality_issues"]:
        for issue in issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    quality = {
        "raw_rows": raw_rows,
        "accepted_rows": int(len(accepted)),
        "quarantined_rows": int(len(quarantined)),
        "quarantine_fraction": 0.0 if raw_rows == 0 else float(len(quarantined) / raw_rows),
        "duplicates": int(issue_counts.get("duplicate_row", 0)),
        "future_rankings": int(issue_counts.get("future_ranking", 0)),
        "invalid_dates": int(issue_counts.get("invalid_date", 0)),
        "unknown_surfaces": int((accepted["surface"] == "unknown").sum()) if len(accepted) else 0,
        "legacy_unverified_rows": int((accepted["lineage_status"] == "legacy_unverified").sum()) if len(accepted) else 0,
        "lineage_verified_rows": int((accepted["lineage_status"] == "verified_pre_match").sum()) if len(accepted) else 0,
        "issue_counts": issue_counts,
    }
    return accepted, quarantined, quality


def _readiness(accepted: pd.DataFrame, quality: dict[str, Any], limits: TennisReadinessLimits) -> dict[str, Any]:
    dates = pd.to_datetime(accepted.get("date"), utc=True, errors="coerce")
    surfaces = accepted.get("surface", pd.Series(dtype=str)).fillna("unknown").astype(str).value_counts().to_dict()
    known_surfaces = {key: int(value) for key, value in surfaces.items() if key != "unknown"}
    rows = int(len(accepted))
    distinct_dates = int(dates.nunique())
    exploratory_surface_count = sum(value >= limits.minimum_surface_rows_exploratory for value in known_surfaces.values())
    challenger_surface_count = sum(value >= limits.minimum_surface_rows_challenger for value in known_surfaces.values())
    exploratory = (
        rows >= limits.exploratory_min_rows
        and distinct_dates >= limits.exploratory_min_dates
        and exploratory_surface_count >= limits.minimum_distinct_surfaces
    )
    challenger = (
        rows >= limits.challenger_min_rows
        and distinct_dates >= limits.challenger_min_dates
        and challenger_surface_count >= limits.minimum_distinct_surfaces
    )
    lineage_complete = quality.get("legacy_unverified_rows", 0) == 0 and quality.get("future_rankings", 0) == 0
    return {
        "status": "challenger_ready" if challenger else ("exploratory_ready" if exploratory else "collecting"),
        "rows": rows,
        "distinct_dates": distinct_dates,
        "surface_counts": known_surfaces,
        "exploratory_ready": bool(exploratory),
        "challenger_ready": bool(challenger),
        "lineage_complete": bool(lineage_complete),
        "gates": {
            "exploratory_rows": {"actual": rows, "required": limits.exploratory_min_rows, "passed": rows >= limits.exploratory_min_rows},
            "exploratory_dates": {"actual": distinct_dates, "required": limits.exploratory_min_dates, "passed": distinct_dates >= limits.exploratory_min_dates},
            "challenger_rows": {"actual": rows, "required": limits.challenger_min_rows, "passed": rows >= limits.challenger_min_rows},
            "challenger_dates": {"actual": distinct_dates, "required": limits.challenger_min_dates, "passed": distinct_dates >= limits.challenger_min_dates},
            "lineage_complete": {"actual": lineage_complete, "required": True, "passed": lineage_complete},
        },
    }


def holdout_generation(dataset: dict[str, Any], accepted: pd.DataFrame, *, generation: int = 1) -> dict[str, Any]:
    dates = pd.Index(sorted(pd.to_datetime(accepted.get("date"), utc=True, errors="coerce").dropna().unique()))
    payload = f"{dataset.get('dataset_id')}:{generation}:{len(dates)}".encode("utf-8")
    identifier = f"HG-{str(dataset.get('sport') or 'sport').upper()}-{sha256(payload).hexdigest()[:20].upper()}"
    if len(dates) < 12:
        return {
            "generation_id": identifier,
            "generation": generation,
            "dataset_id": dataset.get("dataset_id"),
            "sport": dataset.get("sport"),
            "status": "open_collecting",
            "reason": "insufficient_distinct_dates",
            "consulted": False,
        }
    train_end = max(1, int(np.floor(len(dates) * 0.60)))
    calibration_end = max(train_end + 1, int(np.floor(len(dates) * 0.80)))
    calibration_end = min(calibration_end, len(dates) - 1)
    return {
        "generation_id": identifier,
        "generation": generation,
        "dataset_id": dataset.get("dataset_id"),
        "sport": dataset.get("sport"),
        "status": "sealed",
        "train_end": pd.Timestamp(dates[train_end - 1]).isoformat(),
        "calibration_end": pd.Timestamp(dates[calibration_end - 1]).isoformat(),
        "holdout_start": pd.Timestamp(dates[calibration_end]).isoformat(),
        "holdout_end": pd.Timestamp(dates[-1]).isoformat(),
        "consulted": False,
        "retuning_after_consultation_allowed": False,
    }


def build_tennis_dataset_package(
    frame: pd.DataFrame,
    *,
    source: str,
    license_status: str = "unknown",
    supersedes_dataset_id: str | None = None,
    limits: TennisReadinessLimits | None = None,
) -> dict[str, Any]:
    limits = limits or TennisReadinessLimits()
    accepted, quarantined, quality = normalise_tennis_import(frame)
    snapshot = dataset_snapshot(accepted, sport="tennis", source=source)
    readiness = _readiness(accepted, quality, limits)
    license_ok = license_status in {"research_only", "approved"}
    quality_ok = quality["quarantine_fraction"] <= limits.maximum_quarantine_fraction
    if readiness["challenger_ready"] and readiness["lineage_complete"] and license_ok and quality_ok:
        quality_status = "approved_for_training"
    elif len(accepted) and quality_ok:
        quality_status = "validated"
    elif len(accepted):
        quality_status = "draft"
    else:
        quality_status = "quarantined"
    catalog = {
        **snapshot,
        "license_status": license_status,
        "quality_status": quality_status,
        "supersedes_dataset_id": supersedes_dataset_id,
        "competitions": sorted(set(accepted["tournament"].dropna().astype(str)))[:200],
        "tours": sorted(set(accepted["tour"].dropna().astype(str))),
        "surfaces": readiness["surface_counts"],
        "players": int(len(set(accepted["winner_name"]) | set(accepted["loser_name"]))) if len(accepted) else 0,
        "quality": quality,
        "readiness": readiness,
        "provider_credits_consumed": 0,
    }
    generation = holdout_generation(catalog, accepted)
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog": catalog,
        "holdout_generation": generation,
        "accepted": accepted,
        "quarantined": quarantined,
        "limits": asdict(limits),
    }


def _football_components(frame: pd.DataFrame, limits: ChallengerFactoryLimits) -> dict[str, Any] | None:
    features = FootballPredictor().build_features(frame)
    dates = pd.to_datetime(features["date"], utc=True, errors="coerce")
    groups = pd.Index(sorted(dates.unique()))
    holdout_groups = max(2, int(np.ceil(len(groups) * limits.holdout_fraction)))
    calibration_groups = max(2, int(np.ceil(len(groups) * limits.calibration_fraction)))
    train_groups = len(groups) - holdout_groups - calibration_groups
    if train_groups < 4:
        return None
    train_end = groups[train_groups - 1]
    calibration_end = groups[train_groups + calibration_groups - 1]
    train = np.flatnonzero(dates.to_numpy() <= train_end)
    calibration = np.flatnonzero((dates.to_numpy() > train_end) & (dates.to_numpy() <= calibration_end))
    holdout = np.flatnonzero(dates.to_numpy() > calibration_end)
    X = features.loc[:, FOOTBALL_FEATURES].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    y = features["result_class"].astype(int).to_numpy()
    scaler = StandardScaler().fit(X[train])
    model = LogisticRegression(C=1.0, max_iter=800, solver="lbfgs", random_state=42)
    model.fit(scaler.transform(X[train]), y[train])
    temperature = fit_temperature_multiclass(model.predict_proba(scaler.transform(X[calibration])), y[calibration])
    challenger = apply_temperature_multiclass(model.predict_proba(scaler.transform(X[holdout])), temperature)
    baseline = _football_elo_baseline(features.iloc[holdout]["elo_home_prob"].to_numpy(dtype=float))
    return {
        "features": features,
        "target": y,
        "train": train,
        "calibration": calibration,
        "holdout": holdout,
        "challenger": challenger,
        "baseline": baseline,
    }


def _group_metric_rows(
    frame: pd.DataFrame,
    labels: Iterable[str],
    target: np.ndarray,
    challenger: np.ndarray,
    baseline: np.ndarray,
    *,
    minimum_rows: int = 10,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    labels_array = np.asarray(list(labels), dtype=object)
    for label in sorted(set(labels_array)):
        mask = labels_array == label
        rows = int(mask.sum())
        if rows < minimum_rows:
            result[str(label)] = {"rows": rows, "status": "not_evaluable"}
            continue
        challenger_metrics = _multiclass_metrics(target[mask], challenger[mask])
        baseline_metrics = _multiclass_metrics(target[mask], baseline[mask])
        result[str(label)] = {
            "rows": rows,
            "status": "evaluated",
            "challenger": challenger_metrics,
            "baseline": baseline_metrics,
            "delta_log_loss": float(challenger_metrics["log_loss"] - baseline_metrics["log_loss"]),
            "delta_ece": float(challenger_metrics["ece"] - baseline_metrics["ece"]),
        }
    return result


def build_football_hold_analysis(frame: pd.DataFrame, *, limits: ChallengerFactoryLimits | None = None) -> dict[str, Any]:
    limits = limits or ChallengerFactoryLimits()
    snapshot = dataset_snapshot(frame, sport="football", source="local_football_archive")
    components = _football_components(frame, limits)
    if components is None:
        return {
            "status": "collecting",
            "reason": "chronological_partition_unavailable",
            "dataset": snapshot,
            "provider_credits_consumed": 0,
        }
    features = components["features"]
    holdout = components["holdout"]
    hold = features.iloc[holdout].reset_index(drop=True)
    target = components["target"][holdout]
    challenger = components["challenger"]
    baseline = components["baseline"]
    overall_challenger = _multiclass_metrics(target, challenger)
    overall_baseline = _multiclass_metrics(target, baseline)
    confidence = np.max(baseline, axis=1)
    confidence_band = np.where(confidence < 0.45, "balanced", np.where(confidence < 0.60, "moderate_favourite", "strong_favourite"))
    cold_start = np.where((hold["home_matches_seen"] < 5) | (hold["away_matches_seen"] < 5), "cold_start", "established")
    rest_gap = np.abs(hold["home_rest_days"].to_numpy(dtype=float) - hold["away_rest_days"].to_numpy(dtype=float))
    rest_band = np.where(rest_gap >= 4, "rest_imbalance", "similar_rest")
    outcomes = np.asarray(["away", "draw", "home"], dtype=object)[target]
    seasons = pd.to_datetime(hold["date"], utc=True).dt.year.astype(str).to_numpy()
    breakdowns = {
        "outcome": _group_metric_rows(hold, outcomes, target, challenger, baseline),
        "season": _group_metric_rows(hold, seasons, target, challenger, baseline, minimum_rows=20),
        "market_shape": _group_metric_rows(hold, confidence_band, target, challenger, baseline),
        "team_history": _group_metric_rows(hold, cold_start, target, challenger, baseline),
        "rest_context": _group_metric_rows(hold, rest_band, target, challenger, baseline),
    }
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    for dimension, groups in breakdowns.items():
        for group, metrics in groups.items():
            if metrics.get("status") != "evaluated":
                continue
            item = {"dimension": dimension, "group": group, "rows": metrics["rows"], "delta_log_loss": metrics["delta_log_loss"]}
            (regressions if metrics["delta_log_loss"] > 0 else improvements).append(item)
    regressions.sort(key=lambda item: item["delta_log_loss"], reverse=True)
    improvements.sort(key=lambda item: item["delta_log_loss"])
    delta = overall_challenger["log_loss"] - overall_baseline["log_loss"]
    status = "hold_explained" if delta > -limits.log_loss_improvement_required else "candidate_explained"
    return {
        "status": status,
        "reason": "challenger_not_consistently_better_across_holdout_subgroups" if status == "hold_explained" else "challenger_passed_overall_holdout_gate",
        "dataset": snapshot,
        "partitions": {
            "train": int(len(components["train"])),
            "calibration": int(len(components["calibration"])),
            "holdout": int(len(holdout)),
        },
        "overall": {
            "challenger": overall_challenger,
            "baseline": overall_baseline,
            "delta_log_loss": float(delta),
            "delta_ece": float(overall_challenger["ece"] - overall_baseline["ece"]),
        },
        "breakdowns": breakdowns,
        "largest_regressions": regressions[:5],
        "largest_improvements": improvements[:5],
        "bounded_next_round": {
            "maximum_new_challengers": 2,
            "candidates": [
                "regularized_poisson_attack_defence",
                "hybrid_linear_attack_defence_elo",
            ],
            "status": "planned_not_trained",
            "selection_metric": "probabilistic_holdout_quality_not_roi",
        },
        "provider_credits_consumed": 0,
        "automatic_promotion": False,
    }


def build_evidence_acceleration_report(
    *,
    root: Path,
    tennis_path: Path | None = None,
    football_path: Path | None = None,
    source: str = "local_tennis_archive",
    license_status: str = "research_only",
) -> dict[str, Any]:
    tennis_path = tennis_path or root / "data" / "real_snapshot" / "tennis_atp_2025_snapshot.csv"
    football_path = football_path or root / "data" / "real" / "football_epl_2021_2026.csv"
    tennis_package = build_tennis_dataset_package(pd.read_csv(tennis_path), source=source, license_status=license_status)
    football = build_football_hold_analysis(pd.read_csv(football_path))
    tennis_status = tennis_package["catalog"]["readiness"]["status"]
    status = "collecting" if tennis_status == "collecting" else ("review_required" if football["status"] == "candidate_explained" else "hold")
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "football": football,
        "tennis": {
            "catalog": tennis_package["catalog"],
            "holdout_generation": tennis_package["holdout_generation"],
            "quarantined_preview": tennis_package["quarantined"].head(20).to_dict(orient="records"),
        },
        "limits": {
            "provider_credits_consumed": 0,
            "automatic_promotion": False,
            "maximum_new_football_challengers": 2,
            "new_simple_ui_tabs": 0,
        },
        "next_action": (
            "Import a larger, time-audited, multi-surface tennis archive."
            if tennis_status == "collecting"
            else "Review the football hold subgroups before training the bounded next round."
        ),
    }
