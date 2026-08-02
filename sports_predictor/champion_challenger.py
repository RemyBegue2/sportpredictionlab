from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .market_benchmark import BenchmarkPolicy, OUTCOME_ORDER, run_market_benchmark


@dataclass(frozen=True)
class DecisionPolicy:
    exploratory_historical: int = 200
    minimum_historical: int = 1000
    exploratory_live: int = 50
    minimum_live: int = 200
    minimum_favorable_fold_ratio: float = 0.60
    calibration_tolerance: float = 0.01
    require_non_negative_clv: bool = True


def _copy_contender_as_model(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    out = frame.copy()
    missing = [f"{prefix}_{name}" for name in OUTCOME_ORDER if f"{prefix}_{name}" not in out.columns]
    if missing:
        raise ValueError(f"Missing probability columns for contender {prefix}: {missing}")
    for name in OUTCOME_ORDER:
        out[f"model_{name}"] = out[f"{prefix}_{name}"]
    return out


def _fold_stability(report: Mapping[str, Any]) -> dict[str, Any]:
    folds = list(report.get("folds") or [])
    comparable = 0
    favorable = 0
    deltas: list[float] = []
    for fold in folds:
        model = (fold.get("model") or {}).get("log_loss")
        consensus = (fold.get("consensus") or {}).get("log_loss")
        if model is None or consensus is None:
            continue
        comparable += 1
        delta = float(model) - float(consensus)
        deltas.append(delta)
        favorable += int(delta < 0)
    ratio = favorable / comparable if comparable else None
    return {
        "comparable_folds": comparable,
        "favorable_folds": favorable,
        "favorable_ratio": ratio,
        "log_loss_deltas": deltas,
    }


def _contender_summary(name: str, report: Mapping[str, Any]) -> dict[str, Any]:
    aggregate = report.get("aggregate") or {}
    comparison = (report.get("comparisons") or {}).get("model_vs_consensus") or {}
    model = aggregate.get("model") or {}
    consensus = aggregate.get("consensus") or {}
    return {
        "contender": name,
        "evaluated_rows": int(report.get("evaluated_rows") or 0),
        "log_loss": model.get("log_loss"),
        "brier": model.get("brier"),
        "rps": model.get("rps"),
        "ece": model.get("ece"),
        "consensus_log_loss": consensus.get("log_loss"),
        "consensus_ece": consensus.get("ece"),
        "model_minus_consensus_log_loss": comparison.get("mean_left_minus_right_log_loss"),
        "ci95_low": comparison.get("ci95_low"),
        "ci95_high": comparison.get("ci95_high"),
        "fold_stability": _fold_stability(report),
        "closing_line_value": report.get("closing_line_value"),
        "temporal_audit": report.get("temporal_audit"),
        "legacy_verdict": report.get("verdict"),
    }


def run_champion_challenger(
    frame: pd.DataFrame,
    *,
    contenders: Sequence[str] = ("model",),
    benchmark_policy: BenchmarkPolicy | None = None,
) -> dict[str, Any]:
    """Evaluate multiple immutable probability streams on identical folds.

    Every contender is represented by ``<prefix>_away``, ``<prefix>_draw`` and
    ``<prefix>_home`` columns. Winamax and consensus remain common baselines.
    The function never trains on evaluation rows and delegates all temporal
    rejection and expanding-window logic to ``run_market_benchmark``.
    """
    names = [str(name).strip() for name in contenders if str(name).strip()]
    if not names:
        raise ValueError("At least one contender is required")
    reports: dict[str, Any] = {}
    leaderboard: list[dict[str, Any]] = []
    for name in names:
        contender_frame = _copy_contender_as_model(frame, name)
        report = run_market_benchmark(contender_frame, policy=benchmark_policy)
        reports[name] = report
        leaderboard.append(_contender_summary(name, report))
    leaderboard.sort(
        key=lambda row: (
            row.get("log_loss") is None,
            float(row.get("log_loss")) if row.get("log_loss") is not None else np.inf,
            row["contender"],
        )
    )
    return {
        "schema_version": "1.0",
        "protocol": "identical temporally valid rows and expanding-window folds for every contender",
        "outcome_order": list(OUTCOME_ORDER),
        "benchmark_policy": asdict(benchmark_policy or BenchmarkPolicy()),
        "contenders": names,
        "leaderboard": leaderboard,
        "reports": reports,
        "limitations": [
            "Leaderboard order is descriptive until minimum sample and confidence gates are met.",
            "No contender is promoted automatically.",
            "Market consensus is a baseline and must not be used as a historical feature after its observation time.",
        ],
    }


def _live_rows_for_model(shadow_summary: Mapping[str, Any] | None, model_key: str | None) -> int:
    if not shadow_summary:
        return 0
    by_model = shadow_summary.get("by_model_horizon") or {}
    if model_key and model_key in by_model:
        aggregate = (by_model[model_key] or {}).get("aggregate") or {}
        return int(aggregate.get("settled_predictions") or 0)
    aggregate = shadow_summary.get("aggregate") or {}
    return int(aggregate.get("settled_predictions") or 0)


def evaluate_promotion_gates(
    contender: Mapping[str, Any],
    *,
    live_settled: int,
    policy: DecisionPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or DecisionPolicy()
    historical = int(contender.get("evaluated_rows") or 0)
    temporal = contender.get("temporal_audit") or {}
    rejected = int(temporal.get("rejected_rows") or 0)
    ci_high = contender.get("ci95_high")
    model_ece = contender.get("ece")
    consensus_ece = contender.get("consensus_ece")
    stability = contender.get("fold_stability") or {}
    favorable_ratio = stability.get("favorable_ratio")
    clv = contender.get("closing_line_value") or {}
    median_clv = clv.get("median_log_clv")

    gates = {
        "historical_sample": {
            "passed": historical >= policy.minimum_historical,
            "actual": historical,
            "required": policy.minimum_historical,
        },
        "live_shadow_sample": {
            "passed": int(live_settled) >= policy.minimum_live,
            "actual": int(live_settled),
            "required": policy.minimum_live,
        },
        "temporal_integrity": {
            "passed": rejected == 0,
            "rejected_rows": rejected,
        },
        "consensus_advantage": {
            "passed": ci_high is not None and np.isfinite(float(ci_high)) and float(ci_high) < 0,
            "ci95_high": ci_high,
            "criterion": "upper confidence bound below zero",
        },
        "fold_stability": {
            "passed": favorable_ratio is not None and float(favorable_ratio) >= policy.minimum_favorable_fold_ratio,
            "actual": favorable_ratio,
            "required": policy.minimum_favorable_fold_ratio,
        },
        "calibration_non_degraded": {
            "passed": (
                model_ece is not None
                and consensus_ece is not None
                and float(model_ece) <= float(consensus_ece) + policy.calibration_tolerance
            ),
            "model_ece": model_ece,
            "consensus_ece": consensus_ece,
            "tolerance": policy.calibration_tolerance,
        },
        "closing_line_value": {
            "passed": (
                not policy.require_non_negative_clv
                or (median_clv is not None and np.isfinite(float(median_clv)) and float(median_clv) >= 0)
            ),
            "median_log_clv": median_clv,
            "required": ">= 0" if policy.require_non_negative_clv else "not required",
        },
    }

    if historical < policy.exploratory_historical:
        status = "not_evaluable"
        reason = f"Only {historical} historical predictions; {policy.exploratory_historical} are required for an exploratory signal."
    elif historical < policy.minimum_historical or live_settled < policy.minimum_live:
        status = "continue_shadow"
        reason = "Evidence is still preliminary; keep the contender in shadow mode."
    elif all(bool(gate["passed"]) for gate in gates.values()):
        status = "promotion_review"
        reason = "All evidence gates passed; human review is required before any model status transition."
    else:
        status = "no_go"
        failed = [name for name, gate in gates.items() if not gate["passed"]]
        reason = "Promotion blocked by: " + ", ".join(failed)

    return {
        "status": status,
        "reason": reason,
        "historical_predictions": historical,
        "live_shadow_predictions": int(live_settled),
        "gates": gates,
        "automatic_promotion": False,
        "profitability_claim": False,
    }


def build_model_decision(
    benchmark: Mapping[str, Any] | None,
    *,
    shadow_summary: Mapping[str, Any] | None = None,
    champion: str = "model",
    champion_model_key: str | None = None,
    policy: DecisionPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or DecisionPolicy()
    if not benchmark:
        return {
            "schema_version": "1.0",
            "champion": champion,
            "status": "not_evaluable",
            "reason": "No completed champion–challenger benchmark is available.",
            "policy": asdict(policy),
            "leaderboard": [],
            "gates": {},
            "automatic_promotion": False,
            "profitability_claim": False,
        }

    if "leaderboard" in benchmark:
        leaderboard = list(benchmark.get("leaderboard") or [])
    else:
        leaderboard = [_contender_summary(champion, benchmark)]
    selected = next((row for row in leaderboard if row.get("contender") == champion), None)
    if selected is None and leaderboard:
        selected = leaderboard[0]
        champion = str(selected.get("contender") or champion)
    if selected is None:
        return build_model_decision(None, shadow_summary=shadow_summary, champion=champion, policy=policy)

    live_settled = _live_rows_for_model(shadow_summary, champion_model_key)
    verdict = evaluate_promotion_gates(selected, live_settled=live_settled, policy=policy)
    return {
        "schema_version": "1.0",
        "champion": champion,
        "champion_model_key": champion_model_key,
        "status": verdict["status"],
        "reason": verdict["reason"],
        "policy": asdict(policy),
        "leaderboard": leaderboard,
        "selected": dict(selected),
        "gates": verdict["gates"],
        "historical_predictions": verdict["historical_predictions"],
        "live_shadow_predictions": verdict["live_shadow_predictions"],
        "automatic_promotion": False,
        "profitability_claim": False,
        "next_action": {
            "not_evaluable": "Run the reviewed 30-event validation backfill before a full historical collection.",
            "continue_shadow": "Accumulate more temporally valid historical and live shadow observations.",
            "promotion_review": "Open a human promotion review; do not change model status automatically.",
            "no_go": "Keep the current model in shadow and inspect failed evidence gates.",
        }[verdict["status"]],
    }
