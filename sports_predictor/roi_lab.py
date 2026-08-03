from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class SignalPolicy:
    """Research-only policy applied after probability estimation.

    The predictive models are trained for calibrated probabilities. This policy
    is the only component allowed to optimise a simulated financial objective.
    Separating the two prevents a noisy historical ROI from corrupting the
    probability model itself.
    """

    minimum_edge: float = 0.03
    minimum_robust_return: float = 0.02
    maximum_decimal_odds: float = 8.0
    maximum_bets_per_day: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchOpportunity:
    event_id: str
    sport: str
    commence_time: str
    selection: str
    decimal_odds: float
    model_probability: float
    edge: float
    robust_expected_return: float
    won: bool

    @property
    def date(self) -> str:
        parsed = pd.to_datetime(self.commence_time, utc=True, errors="coerce")
        if pd.isna(parsed):
            return "unknown"
        return parsed.date().isoformat()


@dataclass(frozen=True)
class BankrollSimulation:
    starting_bankroll: float
    ending_bankroll: float
    turnover: float
    profit: float
    roi_on_turnover: float | None
    bankroll_return: float
    maximum_drawdown: float
    bets: int
    wins: int
    hit_rate: float | None
    strategy: str
    ruined: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _selection_result(
    *, sport: str, selection: str, fixture: Mapping[str, Any], result_class: str,
) -> bool | None:
    normalized = str(selection).strip().casefold()
    if sport == "football":
        home = str(fixture.get("home_team") or "").strip().casefold()
        away = str(fixture.get("away_team") or "").strip().casefold()
        if normalized == home:
            return result_class == "home"
        if normalized == away:
            return result_class == "away"
        if normalized in {"draw", "match nul", "nul", "x"}:
            return result_class == "draw"
        return None
    if sport == "tennis":
        player_1 = str(fixture.get("player_1") or fixture.get("home_team") or "").strip().casefold()
        player_2 = str(fixture.get("player_2") or fixture.get("away_team") or "").strip().casefold()
        if normalized == player_1:
            return result_class in {"player_1", "home"}
        if normalized == player_2:
            return result_class in {"player_2", "away"}
        return None
    return None


def extract_settled_opportunities(rows: Iterable[Mapping[str, Any]]) -> list[ResearchOpportunity]:
    """Expand settled shadow records into auditable selection opportunities."""

    opportunities: list[ResearchOpportunity] = []
    for row in rows:
        if not bool(row.get("temporal_valid", True)) or str(row.get("status")) != "settled":
            continue
        evaluation = row.get("evaluation") or {}
        result_class = str(evaluation.get("result_class") or "")
        market = row.get("market_analysis") or {}
        fixture = row.get("fixture") or {}
        sport = str(row.get("sport") or "")
        event_id = str(row.get("provider_event_id") or "")
        commence_time = str(row.get("commence_time") or "")
        if not event_id or not result_class or not commence_time:
            continue
        for item in market.get("selections") or []:
            try:
                odds = float(item["decimal_odds"])
                probability = float(item["model_probability"])
                edge = float(item["edge"])
                robust_return = float(item["robust_expected_return"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (1.01 <= odds <= 1000 and 0 < probability < 1):
                continue
            won = _selection_result(
                sport=sport,
                selection=str(item.get("selection") or ""),
                fixture=fixture,
                result_class=result_class,
            )
            if won is None:
                continue
            opportunities.append(ResearchOpportunity(
                event_id=event_id,
                sport=sport,
                commence_time=commence_time,
                selection=str(item.get("selection") or ""),
                decimal_odds=odds,
                model_probability=probability,
                edge=edge,
                robust_expected_return=robust_return,
                won=bool(won),
            ))
    opportunities.sort(key=lambda item: (item.commence_time, item.event_id, -item.robust_expected_return))
    return opportunities


def select_policy_opportunities(
    opportunities: Sequence[ResearchOpportunity], policy: SignalPolicy,
) -> list[ResearchOpportunity]:
    by_event: dict[str, ResearchOpportunity] = {}
    for item in opportunities:
        if item.edge < policy.minimum_edge:
            continue
        if item.robust_expected_return < policy.minimum_robust_return:
            continue
        if item.decimal_odds > policy.maximum_decimal_odds:
            continue
        existing = by_event.get(item.event_id)
        if existing is None or (item.robust_expected_return, item.edge) > (
            existing.robust_expected_return, existing.edge,
        ):
            by_event[item.event_id] = item

    by_day: dict[str, list[ResearchOpportunity]] = {}
    for item in by_event.values():
        by_day.setdefault(item.date, []).append(item)
    selected: list[ResearchOpportunity] = []
    for day in sorted(by_day):
        ranked = sorted(
            by_day[day], key=lambda item: (item.robust_expected_return, item.edge), reverse=True,
        )
        selected.extend(ranked[: max(1, int(policy.maximum_bets_per_day))])
    return sorted(selected, key=lambda item: (item.commence_time, item.event_id))


def _stake_fraction(item: ResearchOpportunity, strategy: str) -> float:
    if strategy == "flat_1pct":
        return 0.01
    if strategy == "flat_2pct":
        return 0.02
    if strategy == "quarter_kelly_capped_2pct":
        b = item.decimal_odds - 1.0
        kelly = (item.model_probability * item.decimal_odds - 1.0) / b if b > 0 else 0.0
        return min(0.02, max(0.0, 0.25 * kelly))
    raise ValueError(f"Unsupported simulation strategy: {strategy}")


def simulate_bankroll(
    opportunities: Sequence[ResearchOpportunity], *, policy: SignalPolicy,
    starting_bankroll: float, strategy: str = "flat_1pct",
) -> BankrollSimulation:
    if not math.isfinite(float(starting_bankroll)) or starting_bankroll <= 0:
        raise ValueError("starting_bankroll must be positive")
    selected = select_policy_opportunities(opportunities, policy)
    bankroll = float(starting_bankroll)
    peak = bankroll
    maximum_drawdown = 0.0
    turnover = 0.0
    wins = 0
    actual_bets = 0
    for item in selected:
        fraction = _stake_fraction(item, strategy)
        stake = min(bankroll, bankroll * fraction)
        if stake <= 0:
            continue
        turnover += stake
        actual_bets += 1
        if item.won:
            bankroll += stake * (item.decimal_odds - 1.0)
            wins += 1
        else:
            bankroll -= stake
        peak = max(peak, bankroll)
        if peak > 0:
            maximum_drawdown = max(maximum_drawdown, (peak - bankroll) / peak)
        if bankroll <= 1e-9:
            bankroll = 0.0
            break
    profit = bankroll - float(starting_bankroll)
    bets = actual_bets
    return BankrollSimulation(
        starting_bankroll=float(starting_bankroll),
        ending_bankroll=float(bankroll),
        turnover=float(turnover),
        profit=float(profit),
        roi_on_turnover=(float(profit / turnover) if turnover > 0 else None),
        bankroll_return=float(profit / float(starting_bankroll)),
        maximum_drawdown=float(maximum_drawdown),
        bets=int(bets),
        wins=int(wins),
        hit_rate=(float(wins / bets) if bets else None),
        strategy=strategy,
        ruined=bankroll <= 0,
    )


def simulate_bankroll_grid(
    opportunities: Sequence[ResearchOpportunity], *, policy: SignalPolicy,
    bankrolls: Sequence[float] = (100.0, 500.0, 1000.0),
    strategies: Sequence[str] = ("flat_1pct", "flat_2pct", "quarter_kelly_capped_2pct"),
) -> list[dict[str, Any]]:
    return [
        simulate_bankroll(
            opportunities, policy=policy, starting_bankroll=float(bankroll), strategy=strategy,
        ).to_dict()
        for bankroll in bankrolls
        for strategy in strategies
    ]


def _policy_grid() -> list[SignalPolicy]:
    return [
        SignalPolicy(edge, robust, max_odds, max_bets)
        for edge in (0.02, 0.03, 0.04, 0.05)
        for robust in (0.00, 0.01, 0.02, 0.03)
        for max_odds in (3.0, 5.0, 8.0)
        for max_bets in (1, 2, 3)
    ]


def _date_groups(opportunities: Sequence[ResearchOpportunity]) -> list[str]:
    return sorted({item.date for item in opportunities if item.date != "unknown"})


def _subset_dates(opportunities: Sequence[ResearchOpportunity], dates: set[str]) -> list[ResearchOpportunity]:
    return [item for item in opportunities if item.date in dates]


def optimise_signal_policy(
    opportunities: Sequence[ResearchOpportunity], *, minimum_settled_events: int = 30,
) -> dict[str, Any]:
    """Tune a signal policy with chronological validation and a final holdout.

    This is intentionally a small deterministic grid. It is faster, auditable,
    and much harder to overfit than unconstrained Bayesian optimisation on a
    noisy ROI objective.
    """

    event_rows = _best_event_opportunities(opportunities)
    unique_events = len(event_rows)
    dates = _date_groups(event_rows)
    if unique_events < minimum_settled_events or len(dates) < 8:
        return {
            "status": "not_evaluable",
            "reason": "insufficient_settled_market_events",
            "settled_events": unique_events,
            "minimum_required": minimum_settled_events,
            "policy": SignalPolicy().to_dict(),
            "holdout": None,
            "cross_validation": None,
        }

    holdout_date_count = max(2, int(math.ceil(len(dates) * 0.20)))
    development_dates = dates[:-holdout_date_count]
    holdout_dates = dates[-holdout_date_count:]
    if len(development_dates) < 6:
        return {
            "status": "not_evaluable",
            "reason": "insufficient_chronological_groups",
            "settled_events": unique_events,
            "minimum_required": minimum_settled_events,
            "policy": SignalPolicy().to_dict(),
            "holdout": None,
            "cross_validation": None,
        }

    fold_count = min(4, max(2, len(development_dates) // 3))
    date_folds = [list(chunk) for chunk in np.array_split(np.asarray(development_dates, dtype=object), fold_count) if len(chunk)]
    candidates: list[dict[str, Any]] = []
    for policy in _policy_grid():
        fold_results: list[dict[str, Any]] = []
        for date_fold in date_folds:
            rows = _subset_dates(opportunities, set(str(item) for item in date_fold))
            simulation = simulate_bankroll(rows, policy=policy, starting_bankroll=1000.0, strategy="flat_1pct")
            fold_results.append(simulation.to_dict())
        bet_counts = [int(item["bets"]) for item in fold_results]
        roi_values = [
            float(item["roi_on_turnover"]) for item in fold_results
            if item["roi_on_turnover"] is not None
        ]
        if sum(bet_counts) < 12 or len(roi_values) < 2:
            score = -999.0
        else:
            median_roi = float(np.median(roi_values))
            instability = float(np.std(roi_values))
            worst_roi = float(min(roi_values))
            max_drawdown = float(max(float(item["maximum_drawdown"]) for item in fold_results))
            score = median_roi - 0.35 * instability - 0.35 * abs(min(0.0, worst_roi)) - 0.20 * max_drawdown
        candidates.append({
            "policy": policy,
            "score": float(score),
            "fold_results": fold_results,
            "bets": int(sum(bet_counts)),
        })
    candidates.sort(key=lambda item: (item["score"], item["bets"]), reverse=True)
    best = candidates[0]
    best_policy: SignalPolicy = best["policy"]
    holdout_rows = _subset_dates(opportunities, set(holdout_dates))
    holdout = simulate_bankroll(
        holdout_rows, policy=best_policy, starting_bankroll=1000.0, strategy="flat_1pct",
    )
    holdout_bets = int(holdout.bets)
    status = "candidate" if holdout_bets >= 5 else "not_evaluable"
    reason = "chronological_holdout_completed" if status == "candidate" else "holdout_has_too_few_signals"
    return {
        "status": status,
        "reason": reason,
        "settled_events": unique_events,
        "development_dates": [development_dates[0], development_dates[-1]],
        "holdout_dates": [holdout_dates[0], holdout_dates[-1]],
        "policy": best_policy.to_dict(),
        "cross_validation": {
            "score": float(best["score"]),
            "bets": int(best["bets"]),
            "folds": best["fold_results"],
            "candidate_policies_evaluated": len(candidates),
        },
        "holdout": holdout.to_dict(),
        "objective": (
            "median chronological ROI minus instability, downside and drawdown penalties; "
            "probability models are not trained directly on ROI"
        ),
    }



def _best_event_opportunities(
    opportunities: Sequence[ResearchOpportunity],
) -> list[ResearchOpportunity]:
    """Keep one pre-match candidate per event for meta-model training.

    A football 1N2 event contributes three mutually exclusive selections and a
    tennis match contributes two. Treating them as independent training rows
    would over-weight each event and make the holdout look larger than it is.
    The research policy can emit at most one signal per event, so the meta-model
    is trained on the same unit of decision: the best pre-match candidate.
    """
    selected: dict[str, ResearchOpportunity] = {}
    for item in opportunities:
        existing = selected.get(item.event_id)
        if existing is None or (item.robust_expected_return, item.edge, item.model_probability) > (
            existing.robust_expected_return, existing.edge, existing.model_probability,
        ):
            selected[item.event_id] = item
    return sorted(selected.values(), key=lambda item: (item.commence_time, item.event_id))


def _meta_features(opportunities: Sequence[ResearchOpportunity]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    rows: list[list[float]] = []
    targets: list[int] = []
    ids: list[str] = []
    for item in opportunities:
        market_probability = float(item.model_probability - item.edge)
        rows.append([
            float(item.model_probability),
            market_probability,
            float(item.edge),
            float(item.robust_expected_return),
            math.log(float(item.decimal_odds)),
            1.0 if item.sport == "tennis" else 0.0,
        ])
        targets.append(1 if item.won else 0)
        ids.append(item.event_id)
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=int), ids


def train_roi_meta_model(
    opportunities: Sequence[ResearchOpportunity], *, minimum_settled_events: int = 60,
) -> dict[str, Any]:
    """Train a compact chronological meta-model for research signal quality.

    It predicts whether a proposed selection wins from pre-match probability and
    market features. The final 20% of dates are untouched until evaluation.
    Model selection uses log loss, while the separate policy optimiser handles
    the simulated ROI objective.
    """
    event_rows = _best_event_opportunities(opportunities)
    unique_events = len(event_rows)
    sport_event_counts: dict[str, int] = {}
    for item in event_rows:
        sport_event_counts[item.sport] = sport_event_counts.get(item.sport, 0) + 1
    dates = _date_groups(event_rows)
    if unique_events < minimum_settled_events or len(dates) < 10:
        return {
            "status": "not_evaluable",
            "reason": "insufficient_settled_events_for_meta_model",
            "settled_events": unique_events,
            "minimum_required": minimum_settled_events,
            "sport_event_counts": sport_event_counts,
        }
    holdout_date_count = max(2, int(math.ceil(len(dates) * 0.20)))
    dev_dates = dates[:-holdout_date_count]
    holdout_dates = dates[-holdout_date_count:]
    validation_count = max(2, int(math.ceil(len(dev_dates) * 0.20)))
    train_dates = dev_dates[:-validation_count]
    validation_dates = dev_dates[-validation_count:]
    train_rows = _subset_dates(event_rows, set(train_dates))
    validation_rows = _subset_dates(event_rows, set(validation_dates))
    holdout_rows = _subset_dates(event_rows, set(holdout_dates))
    x_train, y_train, _ = _meta_features(train_rows)
    x_validation, y_validation, _ = _meta_features(validation_rows)
    x_holdout, y_holdout, _ = _meta_features(holdout_rows)
    if len(np.unique(y_train)) < 2 or len(np.unique(y_validation)) < 2 or len(np.unique(y_holdout)) < 2:
        return {
            "status": "not_evaluable",
            "reason": "chronological_split_has_single_class",
            "settled_events": unique_events,
            "minimum_required": minimum_settled_events,
            "sport_event_counts": sport_event_counts,
        }

    feature_names = [
        "model_probability", "market_probability", "edge",
        "robust_expected_return", "log_decimal_odds", "sport_is_tennis",
    ]
    candidates: list[dict[str, Any]] = []
    for c_value in (0.05, 0.2, 1.0, 5.0):
        scaler = StandardScaler()
        scaled_train = scaler.fit_transform(x_train)
        model = LogisticRegression(C=c_value, max_iter=500, random_state=42)
        model.fit(scaled_train, y_train)
        validation_prob = np.clip(model.predict_proba(scaler.transform(x_validation))[:, 1], 1e-6, 1 - 1e-6)
        candidates.append({
            "c": c_value,
            "loss": float(log_loss(y_validation, validation_prob, labels=[0, 1])),
            "model": model,
            "scaler": scaler,
        })
    candidates.sort(key=lambda item: (item["loss"], item["c"]))
    best = candidates[0]
    model: LogisticRegression = best["model"]
    scaler: StandardScaler = best["scaler"]
    holdout_prob = np.clip(model.predict_proba(scaler.transform(x_holdout))[:, 1], 1e-6, 1 - 1e-6)

    meta_opportunities = [
        ResearchOpportunity(
            event_id=item.event_id,
            sport=item.sport,
            commence_time=item.commence_time,
            selection=item.selection,
            decimal_odds=item.decimal_odds,
            model_probability=float(probability),
            edge=float(probability - (item.model_probability - item.edge)),
            robust_expected_return=float(max(0.001, probability - 0.05) * item.decimal_odds - 1.0),
            won=item.won,
        )
        for item, probability in zip(holdout_rows, holdout_prob, strict=True)
    ]
    holdout_simulation = simulate_bankroll(
        meta_opportunities,
        policy=SignalPolicy(),
        starting_bankroll=1000.0,
        strategy="flat_1pct",
    )
    return {
        "status": "candidate",
        "reason": "chronological_holdout_completed",
        "settled_events": unique_events,
        "sport_event_counts": sport_event_counts,
        "feature_names": feature_names,
        "training_dates": [train_dates[0], train_dates[-1]],
        "validation_dates": [validation_dates[0], validation_dates[-1]],
        "holdout_dates": [holdout_dates[0], holdout_dates[-1]],
        "selected_regularisation_c": float(best["c"]),
        "validation_log_loss": float(best["loss"]),
        "holdout": {
            "rows": int(len(y_holdout)),
            "log_loss": float(log_loss(y_holdout, holdout_prob, labels=[0, 1])),
            "brier": float(brier_score_loss(y_holdout, holdout_prob)),
            "accuracy": float(np.mean((holdout_prob >= 0.5) == y_holdout)),
            "bankroll_simulation": holdout_simulation.to_dict(),
        },
        "portable_parameters": {
            "scaler_mean": scaler.mean_.astype(float).tolist(),
            "scaler_scale": scaler.scale_.astype(float).tolist(),
            "coef": model.coef_[0].astype(float).tolist(),
            "intercept": float(model.intercept_[0]),
        },
        "objective": "probability log loss on chronological validation; ROI remains a separate shadow policy metric",
    }



def score_roi_meta_model(
    *,
    model_probability: float,
    market_probability: float,
    edge: float,
    robust_expected_return: float,
    decimal_odds: float,
    sport: str,
    meta_model: Mapping[str, Any],
) -> float | None:
    """Apply a previously validated portable ROI meta-model.

    The function is deliberately side-effect free so the web process can score
    a current shadow candidate without deserialising an arbitrary model file.
    It returns ``None`` until the chronological holdout has produced a candidate.
    """
    if str(meta_model.get("status") or "") != "candidate":
        return None
    parameters = meta_model.get("portable_parameters") or {}
    try:
        mean = np.asarray(parameters["scaler_mean"], dtype=float)
        scale = np.asarray(parameters["scaler_scale"], dtype=float)
        coef = np.asarray(parameters["coef"], dtype=float)
        intercept = float(parameters["intercept"])
        features = np.asarray([
            float(model_probability),
            float(market_probability),
            float(edge),
            float(robust_expected_return),
            math.log(float(decimal_odds)),
            1.0 if str(sport) == "tennis" else 0.0,
        ], dtype=float)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if mean.shape != features.shape or scale.shape != features.shape or coef.shape != features.shape:
        return None
    if not np.all(np.isfinite(features)) or not np.all(np.isfinite(mean)) or not np.all(np.isfinite(coef)):
        return None
    safe_scale = np.where(np.abs(scale) < 1e-12, 1.0, scale)
    logit = float(intercept + np.dot((features - mean) / safe_scale, coef))
    logit = max(-40.0, min(40.0, logit))
    return float(1.0 / (1.0 + math.exp(-logit)))

def build_roi_lab_report(
    shadow_rows: Sequence[Mapping[str, Any]], *, bankrolls: Sequence[float] = (100.0, 500.0, 1000.0),
) -> dict[str, Any]:
    opportunities = extract_settled_opportunities(shadow_rows)
    optimisation = optimise_signal_policy(opportunities)
    meta_model = train_roi_meta_model(opportunities)
    policy = SignalPolicy(**optimisation.get("policy", SignalPolicy().to_dict()))
    simulations = simulate_bankroll_grid(opportunities, policy=policy, bankrolls=bankrolls)
    sport_counts: dict[str, int] = {}
    for item in opportunities:
        sport_counts[item.sport] = sport_counts.get(item.sport, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "research_only_simulation",
        "opportunities": len(opportunities),
        "unique_events": len({item.event_id for item in opportunities}),
        "sport_selection_rows": sport_counts,
        "optimisation": optimisation,
        "meta_model": meta_model,
        "simulations": simulations,
        "constraints": {
            "automatic_bet_placement": False,
            "real_money_stake_recommendation": False,
            "historical_roi_is_not_a_profitability_claim": True,
            "cold_start_market_signals_allowed": False,
        },
    }
