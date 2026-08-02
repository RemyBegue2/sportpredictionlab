from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class MarketSelection:
    selection: str
    decimal_odds: float
    model_probability: float
    market_probability: float
    fair_odds: float
    edge: float
    expected_return: float
    robust_expected_return: float
    status: str
    reasons: list[str]


@dataclass(frozen=True)
class MarketAnalysis:
    bookmaker: str
    market_type: str
    observed_at: str | None
    odds_age_minutes: float | None
    overround: float
    uncertainty_margin: float
    selections: list[MarketSelection]
    shortlist: list[str]
    warning: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["selections"] = [asdict(x) for x in self.selections]
        return payload


def _validate_probability(value: float) -> float:
    value = float(value)
    if not 0.0 < value < 1.0:
        raise ValueError("Model probabilities must be strictly between 0 and 1")
    return value


def _validate_odds(value: float) -> float:
    value = float(value)
    if not 1.01 <= value <= 1000.0:
        raise ValueError("Decimal odds must be between 1.01 and 1000")
    return value


def _normalise(values: np.ndarray) -> np.ndarray:
    total = float(values.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("Invalid market probabilities")
    return values / total


def _odds_age_minutes(observed_at: str | None, now: datetime | None = None) -> float | None:
    if not observed_at:
        return None
    try:
        parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    parsed_utc = parsed.astimezone(timezone.utc)
    delta_minutes = (reference - parsed_utc).total_seconds() / 60.0
    if delta_minutes < -5.0:
        raise ValueError("observed_at cannot be in the future")
    return max(0.0, delta_minutes)


def analyze_market(
    *,
    labels: Sequence[str],
    model_probabilities: Sequence[float],
    decimal_odds: Sequence[float],
    bookmaker: str = "Winamax",
    market_type: str,
    observed_at: str | None = None,
    uncertainty_margin: float = 0.05,
    minimum_edge: float = 0.03,
    minimum_robust_return: float = 0.02,
    maximum_odds_age_minutes: float = 60.0,
    calibrated: bool = True,
    research_only: bool = True,
    now: datetime | None = None,
) -> MarketAnalysis:
    """Compare model probabilities with a complete bookmaker market.

    This function deliberately does not produce a stake size or place a bet. A
    selection is only marked as a research candidate when the edge survives a
    conservative probability haircut and the odds snapshot is fresh.
    """
    if len(labels) < 2 or len(labels) != len(model_probabilities) or len(labels) != len(decimal_odds):
        raise ValueError("Labels, probabilities and odds must have the same length >= 2")
    if not 0.0 <= uncertainty_margin < 0.5:
        raise ValueError("uncertainty_margin must be in [0, 0.5)")

    probs = np.asarray([_validate_probability(x) for x in model_probabilities], dtype=float)
    if not np.isclose(probs.sum(), 1.0, atol=1e-6):
        raise ValueError("Model probabilities must sum to 1")
    odds = np.asarray([_validate_odds(x) for x in decimal_odds], dtype=float)
    raw_implied = 1.0 / odds
    overround = float(raw_implied.sum() - 1.0)
    market_probs = _normalise(raw_implied)
    age = _odds_age_minutes(observed_at, now=now)

    selections: list[MarketSelection] = []
    shortlist: list[str] = []
    for label, prob, odd, market_prob in zip(labels, probs, odds, market_probs, strict=True):
        fair_odds = 1.0 / prob
        edge = float(prob - market_prob)
        expected_return = float(prob * odd - 1.0)
        conservative_probability = max(0.001, float(prob - uncertainty_margin))
        robust_return = float(conservative_probability * odd - 1.0)
        reasons: list[str] = []

        if not calibrated:
            status = "abstention"
            reasons.append("probabilité non calibrée")
        elif age is None:
            status = "à actualiser"
            reasons.append("heure de la cote absente")
        elif age > maximum_odds_age_minutes:
            status = "à actualiser"
            reasons.append(f"cote âgée de {age:.0f} min")
        elif overround > 0.18:
            status = "abstention"
            reasons.append("marge de marché anormalement élevée")
        elif edge >= minimum_edge and robust_return >= minimum_robust_return:
            status = "candidat recherche" if research_only else "candidat"
            reasons.append("edge positif après marge d'incertitude")
            shortlist.append(str(label))
        elif expected_return > 0:
            status = "surveillance"
            reasons.append("EV brut positif mais non robuste")
        else:
            status = "abstention"
            reasons.append("aucun edge robuste")

        selections.append(MarketSelection(
            selection=str(label),
            decimal_odds=float(odd),
            model_probability=float(prob),
            market_probability=float(market_prob),
            fair_odds=float(fair_odds),
            edge=edge,
            expected_return=expected_return,
            robust_expected_return=robust_return,
            status=status,
            reasons=reasons,
        ))

    selections.sort(key=lambda x: (x.robust_expected_return, x.edge), reverse=True)
    shortlist = [x.selection for x in selections if x.status.startswith("candidat")]
    return MarketAnalysis(
        bookmaker=bookmaker,
        market_type=market_type,
        observed_at=observed_at,
        odds_age_minutes=age,
        overround=overround,
        uncertainty_margin=float(uncertainty_margin),
        selections=selections,
        shortlist=shortlist,
        warning=(
            "Analyse de recherche uniquement. Les cotes changent, le modèle est imparfait et "
            "aucune sélection ne constitue une garantie ou une instruction de mise."
        ),
    )


def analyze_three_way(
    *,
    home_label: str,
    draw_label: str,
    away_label: str,
    home_probability: float,
    draw_probability: float,
    away_probability: float,
    home_odds: float,
    draw_odds: float,
    away_odds: float,
    observed_at: str | None = None,
    uncertainty_margin: float = 0.05,
    calibrated: bool = True,
) -> dict:
    return analyze_market(
        labels=[home_label, draw_label, away_label],
        model_probabilities=[home_probability, draw_probability, away_probability],
        decimal_odds=[home_odds, draw_odds, away_odds],
        market_type="1N2",
        observed_at=observed_at,
        uncertainty_margin=uncertainty_margin,
        calibrated=calibrated,
    ).to_dict()


def analyze_two_way(
    *,
    player_1: str,
    player_2: str,
    player_1_probability: float,
    player_1_odds: float,
    player_2_odds: float,
    observed_at: str | None = None,
    uncertainty_margin: float = 0.06,
    calibrated: bool = True,
) -> dict:
    return analyze_market(
        labels=[player_1, player_2],
        model_probabilities=[player_1_probability, 1.0 - player_1_probability],
        decimal_odds=[player_1_odds, player_2_odds],
        market_type="vainqueur du match",
        observed_at=observed_at,
        uncertainty_margin=uncertainty_margin,
        calibrated=calibrated,
    ).to_dict()
