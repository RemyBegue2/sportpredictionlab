from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import pandas as pd

from .evidence_campaign import BASELINE_MIN_COVERAGE, MATCHING_MIN_COVERAGE
from .version import APP_VERSION

PREFLIGHT_DECISIONS: tuple[str, ...] = ("VIABLE", "RISKY", "NOT_VIABLE")
PREFLIGHT_BASELINES: tuple[str, ...] = ("consensus", "winamax", "pinnacle")
DEFAULT_BOOKMAKERS: tuple[str, ...] = (
    "winamax_fr",
    "betclic_fr",
    "unibet_fr",
    "pmu_fr",
    "pinnacle",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    p = successes / total
    denominator = 1.0 + (z * z / total)
    centre = p + (z * z / (2.0 * total))
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


def _complete_h2h_pairs(odds_rows: pd.DataFrame) -> set[tuple[str, str]]:
    required = {"event_id", "bookmaker_key", "market_key", "outcome_name", "price"}
    if odds_rows.empty or not required.issubset(odds_rows.columns):
        return set()
    rows = odds_rows.copy()
    rows = rows[rows["market_key"].astype(str).eq("h2h")]
    rows["price"] = pd.to_numeric(rows["price"], errors="coerce")
    rows = rows[rows["price"].gt(1.0)]
    if rows.empty:
        return set()
    grouped = rows.groupby(["event_id", "bookmaker_key"], dropna=False)["outcome_name"].nunique()
    return {
        (str(event_id), str(bookmaker))
        for (event_id, bookmaker), outcome_count in grouped.items()
        if int(outcome_count) >= 3
    }


def baseline_ready_event_ids(odds_rows: pd.DataFrame, *, baseline: str) -> set[str]:
    if baseline not in PREFLIGHT_BASELINES:
        raise ValueError(f"baseline must be one of {list(PREFLIGHT_BASELINES)}")
    complete_pairs = _complete_h2h_pairs(odds_rows)
    if baseline == "winamax":
        return {event_id for event_id, bookmaker in complete_pairs if bookmaker == "winamax_fr"}
    if baseline == "pinnacle":
        return {event_id for event_id, bookmaker in complete_pairs if bookmaker == "pinnacle"}
    independent: dict[str, set[str]] = {}
    for event_id, bookmaker in complete_pairs:
        if bookmaker == "winamax_fr":
            continue
        independent.setdefault(event_id, set()).add(bookmaker)
    return {event_id for event_id, bookmakers in independent.items() if len(bookmakers) >= 2}


def bookmaker_coverage_matrix(
    events: pd.DataFrame,
    odds_rows: pd.DataFrame,
    *,
    bookmakers: Sequence[str] = DEFAULT_BOOKMAKERS,
) -> list[dict[str, Any]]:
    if events.empty or "event_id" not in events.columns:
        return []
    event_ids = set(events["event_id"].dropna().astype(str))
    complete_pairs = _complete_h2h_pairs(odds_rows)
    denominator = len(event_ids)
    rows: list[dict[str, Any]] = []
    for bookmaker in bookmakers:
        complete = {event_id for event_id, key in complete_pairs if key == str(bookmaker)} & event_ids
        rows.append(
            {
                "bookmaker_key": str(bookmaker),
                "probed_events": denominator,
                "complete_events": len(complete),
                "coverage": len(complete) / denominator if denominator else 0.0,
            }
        )
    return rows


def _period_rows(events: pd.DataFrame, odds_rows: pd.DataFrame, *, baseline: str) -> list[dict[str, Any]]:
    if events.empty or not {"event_id", "commence_time"}.issubset(events.columns):
        return []
    frame = events[["event_id", "commence_time"]].drop_duplicates("event_id").copy()
    frame["commence_time"] = pd.to_datetime(frame["commence_time"], utc=True, errors="coerce", format="mixed")
    frame = frame.dropna(subset=["commence_time"])
    frame["period"] = frame["commence_time"].dt.tz_convert(None).dt.to_period("Q").astype(str)
    ready = baseline_ready_event_ids(odds_rows, baseline=baseline)
    frame["ready"] = frame["event_id"].astype(str).isin(ready)
    output: list[dict[str, Any]] = []
    for period, group in frame.groupby("period", sort=True):
        total = int(len(group))
        successes = int(group["ready"].sum())
        low, high = wilson_interval(successes, total)
        output.append(
            {
                "period": str(period),
                "probed_events": total,
                "baseline_ready_events": successes,
                "coverage": successes / total if total else 0.0,
                "ci95_low": low,
                "ci95_high": high,
                "start_date": pd.Period(str(period), freq="Q").start_time.date().isoformat(),
                "end_date": pd.Period(str(period), freq="Q").end_time.date().isoformat(),
            }
        )
    return output


def _campaign_type(baseline: str) -> str:
    return "provider_available_benchmark" if baseline == "pinnacle" else "french_market_comparison"


@dataclass(frozen=True)
class CoveragePreflightReport:
    schema_version: str
    app_version: str
    generated_at: str
    source_commit: str
    preflight_plan_id: str | None
    preflight_id: str
    probe_event_ids: list[str]
    probe_event_ids_sha256: str
    baseline_ready_event_ids: list[str]
    odds_evidence_sha256: str
    baseline: str
    campaign_type: str
    target_stage: int
    decision: str
    reason: str
    accepted: bool
    sampled_events: int
    provider_returned_events: int
    baseline_ready_events: int
    provider_coverage: float
    baseline_coverage: float
    baseline_coverage_ci95_low: float
    baseline_coverage_ci95_high: float
    sampling_method: str
    uncertainty_method: str
    uncertainty_limitations: str
    assumed_matching_rate: float
    projected_benchmark_ready_rate: float
    projected_benchmark_ready_events_at_capacity: int
    recommended_selected_events: int | None
    campaign_snapshot_capacity: int
    estimated_snapshot_cost: float
    estimated_discovery_credits: int
    preflight_credits: int
    maximum_preflight_credits: int
    maximum_campaign_credits: int
    bookmaker_coverage: list[dict[str, Any]]
    period_coverage: list[dict[str, Any]]
    candidate_campaign_plan: dict[str, Any] | None
    recommended_followup_preflight: dict[str, Any] | None
    responsible_use: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_coverage_preflight_report(
    events: pd.DataFrame,
    odds_rows: pd.DataFrame,
    *,
    baseline: str,
    target_stage: int,
    maximum_preflight_credits: int,
    maximum_campaign_credits: int,
    preflight_credits: int,
    estimated_snapshot_cost: float = 10.0,
    assumed_matching_rate: float = MATCHING_MIN_COVERAGE,
    minimum_baseline_coverage: float = BASELINE_MIN_COVERAGE,
    source_commit: str = "unknown",
    preflight_plan_id: str | None = None,
    candidate_events: pd.DataFrame | None = None,
) -> CoveragePreflightReport:
    if baseline not in PREFLIGHT_BASELINES:
        raise ValueError(f"baseline must be one of {list(PREFLIGHT_BASELINES)}")
    target_stage = int(target_stage)
    if target_stage <= 0:
        raise ValueError("target_stage must be positive")
    if maximum_preflight_credits < 0 or maximum_campaign_credits < 0:
        raise ValueError("credit caps must be non-negative")
    snapshot_cost = max(1.0, _safe_float(estimated_snapshot_cost, 10.0))
    matching_rate = min(1.0, max(0.0, _safe_float(assumed_matching_rate, MATCHING_MIN_COVERAGE)))

    clean_events = events.copy() if events is not None else pd.DataFrame()
    candidate_source = candidate_events.copy() if candidate_events is not None else clean_events.copy()
    if not clean_events.empty:
        if "event_id" not in clean_events.columns:
            raise ValueError("events must contain event_id")
        clean_events = clean_events.drop_duplicates("event_id")
    if not candidate_source.empty:
        if not {"event_id", "commence_time"}.issubset(candidate_source.columns):
            raise ValueError("candidate_events must contain event_id and commence_time")
        candidate_source = candidate_source.drop_duplicates("event_id").copy()
        candidate_source["commence_time"] = pd.to_datetime(
            candidate_source["commence_time"], utc=True, errors="coerce", format="mixed"
        )
        candidate_source = candidate_source.dropna(subset=["commence_time"])
    event_ids = set(clean_events.get("event_id", pd.Series(dtype=str)).dropna().astype(str))
    returned_ids = set(odds_rows.get("event_id", pd.Series(dtype=str)).dropna().astype(str)) & event_ids
    ready_ids = baseline_ready_event_ids(odds_rows, baseline=baseline) & event_ids
    probe_event_ids = sorted(event_ids)
    ready_event_ids = sorted(ready_ids)
    probe_ids_sha256 = hashlib.sha256(_canonical_json(probe_event_ids).encode("utf-8")).hexdigest()
    evidence_columns = [
        column
        for column in ("event_id", "bookmaker_key", "market_key", "outcome_name", "price", "requested_snapshot_at")
        if column in odds_rows.columns
    ]
    if evidence_columns and not odds_rows.empty:
        evidence_records = odds_rows[evidence_columns].copy()
        for column in evidence_records.columns:
            evidence_records[column] = evidence_records[column].astype(str)
        evidence_records = evidence_records.sort_values(evidence_columns, kind="stable").to_dict(orient="records")
    else:
        evidence_records = []
    odds_evidence_sha256 = hashlib.sha256(_canonical_json(evidence_records).encode("utf-8")).hexdigest()
    sampled = len(event_ids)
    returned = len(returned_ids)
    ready = len(ready_ids)
    provider_coverage = returned / sampled if sampled else 0.0
    baseline_coverage = ready / sampled if sampled else 0.0
    ci_low, ci_high = wilson_interval(ready, sampled)
    projected_ready_rate = baseline_coverage * matching_rate
    recommended_selected = math.ceil(target_stage / projected_ready_rate) if projected_ready_rate > 0 else None
    campaign_discovery_credits = (
        min(180, max(14, math.ceil(recommended_selected / 8)))
        if recommended_selected is not None
        else min(180, max(14, math.ceil(target_stage / 8)))
    )
    available_snapshot_credits = max(0.0, float(maximum_campaign_credits - campaign_discovery_credits))
    campaign_capacity = int(available_snapshot_credits // snapshot_cost)
    projected_ready_at_capacity = int(math.floor(campaign_capacity * projected_ready_rate))

    if sampled == 0:
        decision, reason = "NOT_VIABLE", "no_preflight_events"
    elif preflight_credits > maximum_preflight_credits:
        decision, reason = "NOT_VIABLE", "preflight_credit_cap_exceeded"
    elif ci_high < minimum_baseline_coverage:
        decision, reason = "NOT_VIABLE", "baseline_coverage_upper_bound_below_threshold"
    elif recommended_selected is None or recommended_selected > campaign_capacity:
        decision, reason = "NOT_VIABLE", "campaign_budget_cannot_fund_projected_ready_events"
    elif baseline_coverage >= minimum_baseline_coverage and ci_low >= minimum_baseline_coverage:
        decision, reason = "VIABLE", "coverage_and_budget_supported_by_preflight"
    else:
        decision, reason = "RISKY", "coverage_estimate_is_inconclusive"

    periods = _period_rows(clean_events, odds_rows, baseline=baseline)
    eligible_periods = [row for row in periods if row["probed_events"] >= 3]
    ranked = sorted(
        eligible_periods,
        key=lambda row: (row["ci95_low"], row["coverage"], row["probed_events"]),
        reverse=True,
    )
    best_period = ranked[0] if ranked else None
    start_date = None
    end_date = None
    candidate_pool = candidate_source.copy()
    if best_period and best_period["ci95_low"] >= minimum_baseline_coverage and not candidate_source.empty:
        period_start = pd.Timestamp(best_period["start_date"], tz="UTC")
        period_end = pd.Timestamp(best_period["end_date"], tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        period_pool = candidate_source[
            candidate_source["commence_time"].between(period_start, period_end, inclusive="both")
        ]
        if recommended_selected is not None and len(period_pool) >= recommended_selected:
            candidate_pool = period_pool
            start_date = best_period["start_date"]
            end_date = best_period["end_date"]
    if start_date is None and not candidate_pool.empty:
        start_date = candidate_pool["commence_time"].min().date().isoformat()
        end_date = candidate_pool["commence_time"].max().date().isoformat()
    if decision == "VIABLE" and recommended_selected is not None and len(candidate_pool) < recommended_selected:
        decision, reason = "NOT_VIABLE", "insufficient_discovered_candidate_events"

    candidate_plan: dict[str, Any] | None = None
    if decision == "VIABLE" and recommended_selected is not None and start_date and end_date:
        candidate_ids = sorted(candidate_pool["event_id"].astype(str).unique().tolist())
        candidate_material = {
            "schema_version": "1.0",
            "app_version": APP_VERSION,
            "baseline": baseline,
            "campaign_type": _campaign_type(baseline),
            "target_stage": target_stage,
            "recommended_selected_events": recommended_selected,
            "start_date": start_date,
            "end_date": end_date,
            "maximum_campaign_credits": int(maximum_campaign_credits),
            "estimated_snapshot_cost": round(snapshot_cost, 6),
            "candidate_event_pool_count": len(candidate_ids),
            "candidate_event_ids_sha256": hashlib.sha256(_canonical_json(candidate_ids).encode("utf-8")).hexdigest(),
            "candidate_event_ids": candidate_ids,
            "selection_policy": "chronological_evenly_spaced_without_results",
        }
        candidate_plan = {
            **candidate_material,
            "candidate_plan_id": "CPL-" + hashlib.sha256(_canonical_json(candidate_material).encode("utf-8")).hexdigest()[:24].upper(),
        }

    followup: dict[str, Any] | None = None
    if candidate_plan is None and best_period and best_period["coverage"] >= minimum_baseline_coverage:
        followup = {
            "reason": "promising_period_requires_more_probe_events",
            "start_date": best_period["start_date"],
            "end_date": best_period["end_date"],
            "observed_coverage": best_period["coverage"],
            "observed_events": best_period["probed_events"],
            "minimum_recommended_probe_events": 10,
        }

    material = {
        "schema_version": "1.0",
        "app_version": APP_VERSION,
        "baseline": baseline,
        "campaign_type": _campaign_type(baseline),
        "target_stage": target_stage,
        "preflight_plan_id": preflight_plan_id,
        "probe_event_ids_sha256": probe_ids_sha256,
        "baseline_ready_event_ids": ready_event_ids,
        "odds_evidence_sha256": odds_evidence_sha256,
        "maximum_preflight_credits": int(maximum_preflight_credits),
        "maximum_campaign_credits": int(maximum_campaign_credits),
        "estimated_snapshot_cost": round(snapshot_cost, 6),
        "source_commit": source_commit,
    }
    preflight_id = "PFL-" + hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()[:24].upper()
    return CoveragePreflightReport(
        schema_version="1.0",
        app_version=APP_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_commit=source_commit,
        preflight_plan_id=preflight_plan_id,
        preflight_id=preflight_id,
        probe_event_ids=probe_event_ids,
        probe_event_ids_sha256=probe_ids_sha256,
        baseline_ready_event_ids=ready_event_ids,
        odds_evidence_sha256=odds_evidence_sha256,
        baseline=baseline,
        campaign_type=_campaign_type(baseline),
        target_stage=target_stage,
        decision=decision,
        reason=reason,
        accepted=decision == "VIABLE",
        sampled_events=sampled,
        provider_returned_events=returned,
        baseline_ready_events=ready,
        provider_coverage=provider_coverage,
        baseline_coverage=baseline_coverage,
        baseline_coverage_ci95_low=ci_low,
        baseline_coverage_ci95_high=ci_high,
        sampling_method="deterministic_quarter_stratified_without_outcomes",
        uncertainty_method="wilson_score_diagnostic",
        uncertainty_limitations="Diagnostic only: probes are deterministic, so this is not a formal random-sample population confidence interval.",
        assumed_matching_rate=matching_rate,
        projected_benchmark_ready_rate=projected_ready_rate,
        projected_benchmark_ready_events_at_capacity=projected_ready_at_capacity,
        recommended_selected_events=recommended_selected,
        campaign_snapshot_capacity=campaign_capacity,
        estimated_snapshot_cost=snapshot_cost,
        estimated_discovery_credits=int(campaign_discovery_credits),
        preflight_credits=int(preflight_credits),
        maximum_preflight_credits=int(maximum_preflight_credits),
        maximum_campaign_credits=int(maximum_campaign_credits),
        bookmaker_coverage=bookmaker_coverage_matrix(clean_events, odds_rows),
        period_coverage=periods,
        candidate_campaign_plan=candidate_plan,
        recommended_followup_preflight=followup,
        responsible_use={
            "experimental_analysis": True,
            "profitability_claim": False,
            "stake_recommendation": False,
            "automatic_bet_placement": False,
        },
    )


def validate_preflight_for_campaign(
    report: Mapping[str, Any] | None,
    *,
    baseline: str,
    target_stage: int,
    maximum_campaign_credits: int,
) -> tuple[bool, str]:
    if not report:
        return False, "coverage_preflight_missing"
    if str(report.get("decision") or "") != "VIABLE" or not bool(report.get("accepted")):
        return False, "coverage_preflight_not_viable"
    if str(report.get("baseline") or "") != baseline:
        return False, "coverage_preflight_baseline_mismatch"
    if int(report.get("target_stage") or 0) != int(target_stage):
        return False, "coverage_preflight_target_stage_mismatch"
    if int(report.get("maximum_campaign_credits") or -1) != int(maximum_campaign_credits):
        return False, "coverage_preflight_campaign_budget_mismatch"
    if str(report.get("app_version") or APP_VERSION) != APP_VERSION:
        return False, "coverage_preflight_app_version_mismatch"
    if str(report.get("campaign_type") or "") != "french_market_comparison":
        return False, "coverage_preflight_campaign_type_not_executable"
    candidate = dict(report.get("candidate_campaign_plan") or {})
    candidate_plan_id = str(candidate.pop("candidate_plan_id", ""))
    if not candidate or not candidate_plan_id:
        return False, "coverage_preflight_candidate_plan_missing"
    expected_candidate_id = "CPL-" + hashlib.sha256(_canonical_json(candidate).encode("utf-8")).hexdigest()[:24].upper()
    if candidate_plan_id != expected_candidate_id:
        return False, "coverage_preflight_candidate_plan_integrity_failed"
    candidate_ids = sorted(str(value) for value in candidate.get("candidate_event_ids") or [])
    expected_ids_hash = hashlib.sha256(_canonical_json(candidate_ids).encode("utf-8")).hexdigest()
    if not candidate_ids or str(candidate.get("candidate_event_ids_sha256") or "") != expected_ids_hash:
        return False, "coverage_preflight_candidate_event_pool_integrity_failed"
    if str(candidate.get("app_version") or "") != APP_VERSION:
        return False, "coverage_preflight_candidate_app_version_mismatch"
    if str(candidate.get("baseline") or "") != baseline:
        return False, "coverage_preflight_candidate_baseline_mismatch"
    if int(candidate.get("target_stage") or 0) != int(target_stage):
        return False, "coverage_preflight_candidate_stage_mismatch"
    if int(candidate.get("maximum_campaign_credits") or -1) != int(maximum_campaign_credits):
        return False, "coverage_preflight_candidate_budget_mismatch"
    if str(candidate.get("campaign_type") or "") != "french_market_comparison":
        return False, "coverage_preflight_campaign_type_not_executable"
    if int(candidate.get("candidate_event_pool_count") or -1) != len(candidate_ids):
        return False, "coverage_preflight_candidate_pool_count_mismatch"
    recommended = int(candidate.get("recommended_selected_events") or 0)
    if recommended < int(target_stage):
        return False, "coverage_preflight_candidate_sample_too_small"
    if recommended > len(candidate_ids):
        return False, "coverage_preflight_candidate_pool_too_small"
    return True, "coverage_preflight_viable"
