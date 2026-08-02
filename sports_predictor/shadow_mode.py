from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd


EPS = 1e-12


@dataclass(frozen=True)
class TemporalValidation:
    valid: bool
    issues: list[str]
    prediction_created_at: str
    odds_observed_at: str | None
    commence_time: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_datetime(value: Any, *, required: bool = True) -> datetime | None:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        if required:
            raise ValueError("A valid UTC timestamp is required")
        return None
    return parsed.to_pydatetime()


def validate_temporal_order(
    *,
    prediction_created_at: Any,
    commence_time: Any,
    odds_observed_at: Any | None = None,
) -> TemporalValidation:
    created = utc_datetime(prediction_created_at)
    commence = utc_datetime(commence_time)
    observed = utc_datetime(odds_observed_at, required=False)
    assert created is not None and commence is not None
    issues: list[str] = []
    if created >= commence:
        issues.append("prediction_at_or_after_event_start")
    if observed is not None:
        if observed > created:
            issues.append("odds_observed_after_prediction")
        if observed >= commence:
            issues.append("odds_observed_at_or_after_event_start")
    return TemporalValidation(
        valid=not issues,
        issues=issues,
        prediction_created_at=created.isoformat(),
        odds_observed_at=observed.isoformat() if observed else None,
        commence_time=commence.isoformat(),
    )



def shadow_horizon(*, prediction_created_at: Any, commence_time: Any) -> str | None:
    created = utc_datetime(prediction_created_at)
    commence = utc_datetime(commence_time)
    assert created is not None and commence is not None
    minutes = (commence - created).total_seconds() / 60.0
    if minutes <= 0:
        return None
    # A 15-minute cron cannot guarantee a true closing snapshot. The final
    # live milestone is therefore labelled pre-close and accepts a 20-minute
    # window; the actual closing line remains an after-the-fact benchmark.
    if minutes <= 20:
        return "pre-close"
    if minutes <= 60:
        return "t-1h"
    if minutes <= 360:
        return "t-6h"
    if minutes <= 1440:
        return "t-24h"
    return None

def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def shadow_prediction_hash(
    *,
    provider_event_id: str,
    model_version: str,
    fixture: Mapping[str, Any],
    probabilities: Mapping[str, Any],
    market_analysis: Mapping[str, Any] | None,
    decision: str,
    odds_observed_at: str | None,
    horizon: str | None = None,
) -> str:
    return canonical_payload_hash({
        "provider_event_id": str(provider_event_id),
        "model_version": str(model_version),
        "fixture": dict(fixture),
        "probabilities": dict(probabilities),
        "market_analysis": dict(market_analysis) if market_analysis else None,
        "decision": str(decision),
        "odds_observed_at": odds_observed_at,
        "horizon": horizon,
    })


def football_result_class(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _football_probability_vector(probabilities: Mapping[str, Any]) -> np.ndarray:
    vector = np.asarray([
        float(probabilities["home"]),
        float(probabilities["draw"]),
        float(probabilities["away"]),
    ], dtype=float)
    if not np.isfinite(vector).all() or (vector < 0).any() or vector.sum() <= 0:
        raise ValueError("Invalid football probabilities")
    vector = vector / vector.sum()
    return np.clip(vector, EPS, 1.0)


def _selected_market_item(
    *,
    market_analysis: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if not market_analysis:
        return None
    shortlist = [str(item) for item in market_analysis.get("shortlist", [])]
    if not shortlist:
        return None
    selected = shortlist[0]
    for item in market_analysis.get("selections", []) or []:
        if str(item.get("selection")) == selected:
            return item
    return None


def _selection_outcome(selection: str, fixture: Mapping[str, Any]) -> str | None:
    normalized = selection.strip().casefold()
    home = str(fixture.get("home_team") or "").strip().casefold()
    away = str(fixture.get("away_team") or "").strip().casefold()
    if normalized == home:
        return "home"
    if normalized == away:
        return "away"
    if normalized in {"draw", "match nul", "nul", "x"}:
        return "draw"
    return None


def evaluate_football_shadow(
    *,
    fixture: Mapping[str, Any],
    probabilities: Mapping[str, Any],
    market_analysis: Mapping[str, Any] | None,
    decision: str,
    home_score: int,
    away_score: int,
) -> dict[str, Any]:
    outcome = football_result_class(int(home_score), int(away_score))
    p = _football_probability_vector(probabilities)
    index = {"home": 0, "draw": 1, "away": 2}[outcome]
    target = np.zeros(3, dtype=float)
    target[index] = 1.0
    log_loss = float(-math.log(float(p[index])))
    brier = float(np.sum((p - target) ** 2))
    # Football outcomes are ordinal as away, draw, home for RPS.
    ordinal_p = p[[2, 1, 0]]
    ordinal_target = target[[2, 1, 0]]
    rps = float(np.sum((np.cumsum(ordinal_p)[:-1] - np.cumsum(ordinal_target)[:-1]) ** 2) / 2.0)
    predicted = ("home", "draw", "away")[int(np.argmax(p))]

    selected = _selected_market_item(market_analysis=market_analysis)
    theoretical_return: float | None = None
    selected_outcome: str | None = None
    selected_odds: float | None = None
    if decision == "candidat recherche" and selected:
        selected_outcome = _selection_outcome(str(selected.get("selection") or ""), fixture)
        try:
            selected_odds = float(selected.get("decimal_odds"))
        except (TypeError, ValueError):
            selected_odds = None
        if selected_outcome and selected_odds and selected_odds > 1.0:
            theoretical_return = selected_odds - 1.0 if selected_outcome == outcome else -1.0

    return {
        "result_class": outcome,
        "home_score": int(home_score),
        "away_score": int(away_score),
        "log_loss": log_loss,
        "brier": brier,
        "rps": rps,
        "correct_top_pick": predicted == outcome,
        "predicted_class": predicted,
        "selected_outcome": selected_outcome,
        "selected_odds": selected_odds,
        "theoretical_unit_return": theoretical_return,
        "evaluation_mode": "flat_one_unit_research_only",
    }


def sample_maturity(n: int) -> dict[str, str]:
    if n < 100:
        return {"status": "anecdotal", "label": "anecdotique"}
    if n < 300:
        return {"status": "exploratory", "label": "exploratoire"}
    if n < 500:
        return {"status": "preliminary", "label": "signal préliminaire"}
    return {"status": "evaluation", "label": "première évaluation sérieuse"}


def aggregate_shadow_evaluations(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    settled = [row for row in rows if row.get("evaluation")]
    n = len(settled)
    if not settled:
        return {
            "settled_predictions": 0,
            "maturity": sample_maturity(0),
            "log_loss": None,
            "brier": None,
            "rps": None,
            "accuracy": None,
            "candidate_predictions": 0,
            "candidate_settled": 0,
            "theoretical_unit_return": None,
            "theoretical_roi_per_candidate": None,
        }
    evaluations = [dict(row["evaluation"]) for row in settled]
    candidate_returns = [
        float(item["theoretical_unit_return"])
        for item in evaluations
        if item.get("theoretical_unit_return") is not None
    ]
    candidate_predictions = sum(str(row.get("decision")) == "candidat recherche" for row in rows)
    return {
        "settled_predictions": n,
        "maturity": sample_maturity(n),
        "log_loss": float(np.mean([float(item["log_loss"]) for item in evaluations])),
        "brier": float(np.mean([float(item["brier"]) for item in evaluations])),
        "rps": float(np.mean([float(item["rps"]) for item in evaluations])),
        "accuracy": float(np.mean([bool(item["correct_top_pick"]) for item in evaluations])),
        "candidate_predictions": int(candidate_predictions),
        "candidate_settled": len(candidate_returns),
        "theoretical_unit_return": float(sum(candidate_returns)) if candidate_returns else None,
        "theoretical_roi_per_candidate": float(np.mean(candidate_returns)) if candidate_returns else None,
    }
