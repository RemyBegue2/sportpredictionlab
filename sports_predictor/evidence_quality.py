from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from .evidence_campaign import (
    BASELINE_MIN_COVERAGE,
    BASELINES,
    MATCHING_MIN_COVERAGE,
    PROVIDER_MIN_COVERAGE,
)
from .version import APP_VERSION


@dataclass(frozen=True)
class QualityGate:
    status: str
    reason: str
    accepted: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_event_id(row: Mapping[str, Any]) -> str:
    commence = pd.to_datetime(row.get("commence_time"), utc=True, errors="raise", format="mixed")
    parts = [
        str(row.get("sport_key") or "").strip().casefold(),
        str(row.get("home_team") or "").strip().casefold(),
        str(row.get("away_team") or "").strip().casefold(),
        commence.floor("5min").isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def temporal_row_audit(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        return frame.copy(), pd.DataFrame(columns=["row_index", "event_id", "issues"])
    required = {"event_id", "commence_time", "requested_snapshot_at"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing temporal columns: {sorted(missing)}")
    work = frame.copy()
    work["commence_time"] = pd.to_datetime(work["commence_time"], utc=True, errors="coerce", format="mixed")
    work["requested_snapshot_at"] = pd.to_datetime(work["requested_snapshot_at"], utc=True, errors="coerce", format="mixed")
    issues: list[dict[str, Any]] = []
    valid_mask: list[bool] = []
    for index, row in work.iterrows():
        row_issues: list[str] = []
        if pd.isna(row["commence_time"]):
            row_issues.append("invalid_event_commence_time")
        if pd.isna(row["requested_snapshot_at"]):
            row_issues.append("invalid_odds_observed_at")
        if not row_issues and not (row["requested_snapshot_at"] < row["commence_time"]):
            row_issues.append("odds_not_strictly_before_event")
        valid = not row_issues
        valid_mask.append(valid)
        if row_issues:
            issues.append(
                {
                    "row_index": int(index) if isinstance(index, int) else str(index),
                    "event_id": row.get("event_id"),
                    "issues": row_issues,
                }
            )
    return work.loc[valid_mask].copy(), pd.DataFrame(issues)


def _unique_event_ids(frame: pd.DataFrame | None) -> set[str]:
    if frame is None or frame.empty or "event_id" not in frame.columns:
        return set()
    return {str(value) for value in frame["event_id"].dropna().astype(str) if str(value)}


def _target_key_frame(frame: pd.DataFrame | None, *, snapshot_column: str | None = None) -> pd.DataFrame:
    if frame is None or frame.empty or "event_id" not in frame.columns:
        return pd.DataFrame(columns=["event_id", "snapshot_key"])
    data = frame.copy()
    candidate = snapshot_column
    if candidate is None:
        candidate = next(
            (name for name in ("snapshot_key", "snapshot_at", "requested_snapshot_at", "snapshot_time") if name in data.columns),
            None,
        )
    if candidate is None:
        data["snapshot_key"] = "single"
    elif candidate == "snapshot_key":
        data["snapshot_key"] = data[candidate].astype("string").fillna("single")
    else:
        parsed = pd.to_datetime(data[candidate], utc=True, errors="coerce", format="mixed")
        data["snapshot_key"] = parsed.astype("string").fillna(data[candidate].astype("string"))
    data["event_id"] = data["event_id"].astype(str)
    return data[["event_id", "snapshot_key"]].drop_duplicates().reset_index(drop=True)


def _matching_counts(matches: pd.DataFrame | None, eligible_event_ids: set[str] | None = None) -> dict[str, int]:
    statuses = {"exact": 0, "high_confidence": 0, "manual_review": 0, "collision": 0, "rejected": 0}
    if matches is None or matches.empty:
        return statuses
    data = matches.copy()
    if eligible_event_ids is not None and "provider_event_id" in data.columns:
        data = data[data["provider_event_id"].astype(str).isin(eligible_event_ids)]
    for row in data.to_dict(orient="records"):
        raw = str(row.get("status") or "").casefold()
        confidence = float(row.get("confidence") or 0.0)
        if raw == "matched" and confidence >= 0.995:
            statuses["exact"] += 1
        elif raw == "matched" and confidence >= 0.90:
            statuses["high_confidence"] += 1
        elif raw in {"ambiguous", "manual_review"}:
            statuses["manual_review"] += 1
        elif raw == "collision":
            statuses["collision"] += 1
        else:
            statuses["rejected"] += 1
    return statuses


def _reliable_match_event_ids(matches: pd.DataFrame | None, eligible_event_ids: set[str] | None = None) -> set[str]:
    if matches is None or matches.empty or "provider_event_id" not in matches.columns:
        return set()
    data = matches.copy()
    if eligible_event_ids is not None:
        data = data[data["provider_event_id"].astype(str).isin(eligible_event_ids)]
    confidence = pd.to_numeric(data.get("confidence"), errors="coerce").fillna(0.0)
    reliable = data[data.get("status").astype(str).eq("matched") & confidence.ge(0.90)]
    return set(reliable["provider_event_id"].astype(str))


def _complete_h2h_markets(clean: pd.DataFrame) -> pd.DataFrame:
    columns = ["event_id", "snapshot_key", "bookmaker_key", "complete"]
    required = {"event_id", "bookmaker_key", "market_key", "outcome_name"}
    if clean.empty or not required.issubset(clean.columns):
        return pd.DataFrame(columns=columns)
    data = clean[clean["market_key"].astype(str).eq("h2h")].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    data = data.merge(_target_key_frame(data, snapshot_column="requested_snapshot_at"), on="event_id", how="left", suffixes=("", "_key")) if "requested_snapshot_at" not in data.columns else data
    if "snapshot_key" not in data.columns:
        parsed = pd.to_datetime(data.get("requested_snapshot_at"), utc=True, errors="coerce", format="mixed")
        data["snapshot_key"] = parsed.astype("string").fillna("single")
    rows: list[dict[str, Any]] = []
    for (event_id, snapshot_key, bookmaker), group in data.groupby(
        ["event_id", "snapshot_key", "bookmaker_key"], dropna=False, sort=False
    ):
        outcomes = {str(value).strip().casefold() for value in group["outcome_name"].dropna()}
        home = str(group["home_team"].iloc[0]).strip().casefold() if "home_team" in group.columns else ""
        away = str(group["away_team"].iloc[0]).strip().casefold() if "away_team" in group.columns else ""
        named_complete = bool(home and away and home in outcomes and away in outcomes and "draw" in outcomes)
        generic_complete = {"home", "draw", "away"}.issubset(outcomes)
        valid_prices = True
        if "price" in group.columns:
            prices = pd.to_numeric(group["price"], errors="coerce")
            valid_prices = bool(prices.notna().sum() >= 3 and (prices.dropna() > 1.0).all())
        rows.append(
            {
                "event_id": str(event_id),
                "snapshot_key": str(snapshot_key),
                "bookmaker_key": str(bookmaker),
                "complete": bool((named_complete or generic_complete) and valid_prices),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _bookmaker_coverage(
    clean: pd.DataFrame,
    *,
    targets: pd.DataFrame | None,
    requested_bookmakers: Sequence[str],
    winamax_key: str = "winamax_fr",
) -> tuple[list[dict[str, Any]], int, int, int, set[str], set[str]]:
    target_keys = _target_key_frame(targets)
    if target_keys.empty:
        target_keys = _target_key_frame(clean, snapshot_column="requested_snapshot_at")
    denominator = int(len(target_keys))
    complete = _complete_h2h_markets(clean)
    complete = complete[complete["complete"]] if not complete.empty else complete
    if not complete.empty and not target_keys.empty:
        complete = complete.merge(target_keys, on=["event_id", "snapshot_key"], how="inner")
    rows: list[dict[str, Any]] = []
    for bookmaker in requested_bookmakers:
        present = complete[complete["bookmaker_key"].astype(str).eq(str(bookmaker))] if not complete.empty else complete
        present_count = int(present[["event_id", "snapshot_key"]].drop_duplicates().shape[0]) if not present.empty else 0
        rows.append(
            {
                "bookmaker_key": str(bookmaker),
                "requested_event_snapshots": denominator,
                "complete_event_snapshots": present_count,
                "missing_or_incomplete_event_snapshots": max(0, denominator - present_count),
                "coverage": present_count / denominator if denominator else None,
            }
        )
    if complete.empty:
        return rows, denominator, 0, 0, set(), set()

    independent = complete[~complete["bookmaker_key"].astype(str).eq(winamax_key)].copy()
    independent_grouped = independent.groupby(["event_id", "snapshot_key"], dropna=False)["bookmaker_key"].nunique()
    consensus_keys = {
        (str(event_id), str(snapshot_key))
        for (event_id, snapshot_key), count in independent_grouped.items()
        if int(count) >= 2
    }
    winamax_rows = complete[complete["bookmaker_key"].astype(str).eq(winamax_key)][["event_id", "snapshot_key"]].drop_duplicates()
    winamax_keys = {(str(row.event_id), str(row.snapshot_key)) for row in winamax_rows.itertuples(index=False)}
    consensus_event_ids = {event_id for event_id, _ in consensus_keys}
    winamax_event_ids = {event_id for event_id, _ in winamax_keys}
    return rows, denominator, len(consensus_keys), len(winamax_keys), consensus_event_ids, winamax_event_ids


def _gate(status: str, reason: str, accepted: bool) -> dict[str, Any]:
    return QualityGate(status, reason, accepted).to_dict()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _selection_ledger(
    events: pd.DataFrame,
    *,
    targets: pd.DataFrame | None,
    clean: pd.DataFrame,
    temporal_issues: pd.DataFrame,
    matches: pd.DataFrame | None,
    event_selection: pd.DataFrame | None,
) -> tuple[list[dict[str, Any]], str]:
    event_rows = events.drop_duplicates("event_id").copy() if not events.empty and "event_id" in events.columns else pd.DataFrame()
    if event_rows.empty:
        return [], "unavailable"
    selected_ids = _unique_event_ids(targets) or _unique_event_ids(clean)
    returned_ids = _unique_event_ids(clean)
    temporal_ids = _unique_event_ids(temporal_issues)
    explicit_selection: dict[str, str] = {}
    source = "legacy_reconstructed"
    if event_selection is not None and not event_selection.empty and {"event_id", "selection_status"}.issubset(event_selection.columns):
        explicit_selection = {
            str(row["event_id"]): str(row["selection_status"])
            for row in event_selection[["event_id", "selection_status"]].to_dict(orient="records")
        }
        source = "explicit_v3_9"
    match_by_event: dict[str, tuple[str, float]] = {}
    if matches is not None and not matches.empty and "provider_event_id" in matches.columns:
        for row in matches.to_dict(orient="records"):
            match_by_event[str(row.get("provider_event_id"))] = (
                str(row.get("status") or "unmatched"),
                float(row.get("confidence") or 0.0),
            )
    ledger: list[dict[str, Any]] = []
    for row in event_rows.to_dict(orient="records"):
        event_id = str(row.get("event_id"))
        selection = explicit_selection.get(event_id)
        if event_id not in selected_ids:
            status = selection or "not_selected_sample_or_budget_limit"
        elif event_id in temporal_ids:
            status = "temporal_violation"
        elif event_id not in returned_ids:
            status = "provider_event_missing"
        else:
            match_status, confidence = match_by_event.get(event_id, ("not_evaluated", 0.0))
            if match_status == "ambiguous":
                status = "matching_ambiguous"
            elif match_status == "collision":
                status = "matching_collision"
            elif match_status in {"unmatched", "rejected"}:
                status = "result_missing_or_unmatched"
            else:
                status = "accepted"
            row["matching_confidence"] = confidence
        ledger.append(
            {
                "event_id": event_id,
                "commence_time": str(row.get("commence_time") or ""),
                "home_team": str(row.get("home_team") or ""),
                "away_team": str(row.get("away_team") or ""),
                "status": status,
                "matching_confidence": row.get("matching_confidence"),
            }
        )
    return ledger, source


def build_evidence_quality_report(
    *,
    plan: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    odds_rows: pd.DataFrame,
    events: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
    benchmark: Mapping[str, Any] | None = None,
    requests: pd.DataFrame | None = None,
    targets: pd.DataFrame | None = None,
    discovery_state: Mapping[str, Any] | None = None,
    event_selection: pd.DataFrame | None = None,
    campaign_plan: Mapping[str, Any] | None = None,
    baseline: str | None = None,
    target_stage: int | None = None,
) -> dict[str, Any]:
    """Build a canonical V4.2 evidence report.

    Every consumer receives the same PASS/HOLD/FAIL verdict. Provider coverage
    uses completed targets only, consensus excludes Winamax and requires two
    independent bookmakers, and progression counts only unique events that are
    temporal-valid, reliably matched and ready for the selected baseline.
    """

    plan = dict(plan or {})
    state = dict(state or {})
    campaign_plan = dict(campaign_plan or {})
    discovery_state = dict(discovery_state or {})
    baseline = str(baseline or campaign_plan.get("baseline") or "consensus")
    if baseline not in BASELINES:
        raise ValueError(f"baseline must be one of {list(BASELINES)}")
    resolved_target_stage = int(target_stage or campaign_plan.get("target_stage") or 30)
    if resolved_target_stage <= 0:
        raise ValueError("target_stage must be positive")

    events = events.copy() if events is not None else pd.DataFrame()
    requests = requests.copy() if requests is not None else pd.DataFrame()
    targets = targets.copy() if targets is not None else pd.DataFrame()
    clean, temporal_issues = temporal_row_audit(odds_rows) if not odds_rows.empty else (odds_rows.copy(), pd.DataFrame())

    duplicate_columns = [
        column
        for column in ("event_id", "bookmaker_key", "market_key", "outcome_name", "requested_snapshot_at")
        if column in odds_rows.columns
    ]
    duplicate_rows = int(odds_rows.duplicated(duplicate_columns).sum()) if duplicate_columns else 0
    total_rows = int(len(odds_rows))
    accepted_rows = int(len(clean))

    discovered_event_ids = _unique_event_ids(events)
    selected_event_ids = _unique_event_ids(targets)
    if not selected_event_ids:
        selected_event_ids = _unique_event_ids(clean)
    returned_event_ids = _unique_event_ids(clean)

    discovered_events = len(discovered_event_ids) or _safe_int(discovery_state.get("event_count"))
    requested_events = _safe_int(plan.get("requested_event_count"), discovered_events)
    selected_events = len(selected_event_ids) or _safe_int(plan.get("event_count"), discovered_events)
    requested_events = min(discovered_events, max(selected_events, requested_events)) if discovered_events else max(selected_events, requested_events)

    target_keys = _target_key_frame(targets)
    planned_event_snapshots = int(len(target_keys)) or _safe_int(plan.get("target_count"), selected_events)
    planned_requests = int(len(requests)) or _safe_int(plan.get("request_count"), planned_event_snapshots)
    completed_numbers = {int(value) for value in state.get("completed", []) if str(value).strip().lstrip("-").isdigit()}
    completed_requests = len(completed_numbers)
    if not completed_numbers and str(state.get("status") or "") == "completed":
        completed_requests = planned_requests

    completed_target_keys = target_keys
    if completed_numbers and not requests.empty and "request_number" in requests.columns and "snapshot_at" in requests.columns and not target_keys.empty:
        completed_snapshots = set(
            pd.to_datetime(
                requests.loc[requests["request_number"].astype(int).isin(completed_numbers), "snapshot_at"],
                utc=True,
                errors="coerce",
                format="mixed",
            ).astype("string")
        )
        completed_target_keys = target_keys[target_keys["snapshot_key"].isin(completed_snapshots)]
    completed_event_snapshots = int(len(completed_target_keys)) if not completed_target_keys.empty else (selected_events if completed_requests else 0)

    returned_keys = _target_key_frame(clean, snapshot_column="requested_snapshot_at")
    if not returned_keys.empty and not completed_target_keys.empty:
        returned_keys = returned_keys.merge(
            completed_target_keys, on=["event_id", "snapshot_key"], how="inner"
        ).drop_duplicates(["event_id", "snapshot_key"])
    returned_event_ids = _unique_event_ids(returned_keys)
    returned_event_snapshots = int(len(returned_keys))
    accepted_event_snapshots = returned_event_snapshots
    accepted_events = len(returned_event_ids)

    requested_bookmakers = [str(value) for value in plan.get("bookmakers") or []]
    if not requested_bookmakers and "bookmaker_key" in clean.columns:
        requested_bookmakers = sorted(clean["bookmaker_key"].dropna().astype(str).unique().tolist())
    (
        bookmaker_coverage,
        bookmaker_denominator,
        consensus_ready,
        winamax_ready,
        consensus_ready_ids,
        winamax_ready_ids,
    ) = _bookmaker_coverage(
        clean,
        targets=completed_target_keys,
        requested_bookmakers=requested_bookmakers,
    )

    matching = _matching_counts(matches, returned_event_ids if returned_event_ids else None)
    matched_total = matching["exact"] + matching["high_confidence"]
    matching_denominator = sum(matching.values())
    matching_rate = matched_total / matching_denominator if matching_denominator else None
    matching_collisions = int(matching.get("collision") or 0)
    reliable_match_ids = _reliable_match_event_ids(matches, returned_event_ids if returned_event_ids else None)
    consensus_benchmark_ready_ids = returned_event_ids & reliable_match_ids & consensus_ready_ids
    winamax_benchmark_ready_ids = returned_event_ids & reliable_match_ids & winamax_ready_ids
    benchmark_ready_events_by_baseline = {
        "consensus": len(consensus_benchmark_ready_ids),
        "winamax": len(winamax_benchmark_ready_ids),
    }
    benchmark_ready_ids = (
        consensus_benchmark_ready_ids if baseline == "consensus" else winamax_benchmark_ready_ids
    )
    benchmark_ready_events = len(benchmark_ready_ids)

    temporal_violation_rate = len(temporal_issues) / total_rows if total_rows else 0.0
    duplicate_rate = duplicate_rows / total_rows if total_rows else 0.0
    provider_coverage_rate = returned_event_snapshots / completed_event_snapshots if completed_event_snapshots else 0.0
    consensus_coverage_rate = consensus_ready / bookmaker_denominator if bookmaker_denominator else 0.0
    winamax_coverage_rate = winamax_ready / bookmaker_denominator if bookmaker_denominator else 0.0

    discovery_credits = _safe_int(discovery_state.get("consumed_credits"))
    snapshot_credits = _safe_int(state.get("consumed_credits"))
    total_credits = discovery_credits + snapshot_credits
    global_credit_cap = _safe_int(campaign_plan.get("max_credits"), _safe_int(plan.get("max_credits")))

    integrity_fail_reasons: list[str] = []
    technical_hold_reasons: list[str] = []
    if total_rows == 0:
        technical_hold_reasons.append("no_historical_odds_rows")
    if temporal_violation_rate > 0:
        integrity_fail_reasons.append("temporal_violations_detected")
    if duplicate_rows > 0:
        integrity_fail_reasons.append("duplicate_rows_detected")
    if matching_collisions > 0:
        integrity_fail_reasons.append("matching_collisions_detected")
    if state and str(state.get("status") or "") != "completed":
        technical_hold_reasons.append("backfill_not_completed")
    if global_credit_cap and total_credits > global_credit_cap:
        integrity_fail_reasons.append("credit_cap_exceeded")
    if integrity_fail_reasons:
        integrity_gate = _gate("FAIL", integrity_fail_reasons[0], False)
    elif technical_hold_reasons:
        integrity_gate = _gate("HOLD", technical_hold_reasons[0], False)
    else:
        integrity_gate = _gate("PASS", "temporal, duplicate, matching and budget controls passed", True)

    if completed_event_snapshots == 0:
        provider_gate = _gate("HOLD", "no_completed_provider_target", False)
    elif provider_coverage_rate < PROVIDER_MIN_COVERAGE:
        provider_gate = _gate("HOLD", "provider_return_rate_below_80_percent", False)
    else:
        provider_gate = _gate("PASS", "provider coverage passed on completed targets", True)

    if matches is None or matches.empty:
        matching_gate = _gate("HOLD", "result_matching_not_available", False)
    elif matching_denominator == 0:
        matching_gate = _gate("HOLD", "no_returned_event_eligible_for_matching", False)
    elif matching_rate is not None and matching_rate < MATCHING_MIN_COVERAGE:
        matching_gate = _gate("HOLD", "reliable_matching_below_95_percent", False)
    else:
        matching_gate = _gate("PASS", "reliable matching passed on returned events", True)

    if bookmaker_denominator == 0:
        consensus_gate = _gate("HOLD", "no_complete_market_target", False)
        winamax_gate = _gate("HOLD", "no_complete_market_target", False)
    else:
        consensus_gate = (
            _gate("PASS", "two independent bookmakers cover at least 70 percent of targets", True)
            if consensus_coverage_rate >= BASELINE_MIN_COVERAGE
            else _gate("HOLD", "consensus_coverage_below_70_percent", False)
        )
        winamax_gate = (
            _gate("PASS", "Winamax covers at least 70 percent of targets", True)
            if winamax_coverage_rate >= BASELINE_MIN_COVERAGE
            else _gate("HOLD", "winamax_coverage_below_70_percent", False)
        )
    selected_baseline_gate = consensus_gate if baseline == "consensus" else winamax_gate

    if benchmark_ready_events < 30:
        statistical_gate = _gate("HOLD", "fewer_than_30_benchmark_ready_events", False)
    elif benchmark_ready_events < 100:
        statistical_gate = _gate("HOLD", "30_to_99_events_pipeline_validation_only", False)
    elif benchmark_ready_events < 300:
        statistical_gate = _gate("HOLD", "100_to_299_events_exploratory_only", False)
    elif benchmark_ready_events < 1000:
        statistical_gate = _gate("HOLD", "300_to_999_events_preliminary_only", False)
    else:
        statistical_gate = _gate("PASS", "at_least_1000_benchmark_ready_events", True)

    hold_reasons: list[str] = list(technical_hold_reasons)
    for gate in (provider_gate, matching_gate, selected_baseline_gate):
        if not gate["accepted"]:
            hold_reasons.append(str(gate["reason"]))
    if benchmark_ready_events < resolved_target_stage:
        hold_reasons.append(f"benchmark_ready_events_below_target_{resolved_target_stage}")

    if integrity_fail_reasons:
        decision_gate = QualityGate("FAIL", integrity_fail_reasons[0], False)
    elif hold_reasons:
        decision_gate = QualityGate("HOLD", hold_reasons[0], False)
    else:
        decision_gate = QualityGate("PASS", "all canonical quality and stage checks passed", True)

    warnings: list[str] = []
    if statistical_gate["status"] != "PASS":
        warnings.append(str(statistical_gate["reason"]))
    if baseline == "consensus" and not winamax_gate["accepted"]:
        warnings.append("winamax_coverage_insufficient_for_dedicated_comparison")
    if baseline == "winamax" and not consensus_gate["accepted"]:
        warnings.append("consensus_coverage_insufficient_for_secondary_comparison")

    ledger, selection_source = _selection_ledger(
        events,
        targets=targets,
        clean=clean,
        temporal_issues=temporal_issues,
        matches=matches,
        event_selection=event_selection,
    )
    outcome_counts: dict[str, int] = {}
    for row in ledger:
        outcome_counts[row["status"]] = outcome_counts.get(row["status"], 0) + 1

    benchmark_summary = None
    if benchmark:
        benchmark_summary = {
            "evaluated_rows": _safe_int(benchmark.get("evaluated_rows")),
            "verdict": benchmark.get("verdict"),
            "comparisons": benchmark.get("comparisons"),
            "closing_line_value": benchmark.get("closing_line_value"),
        }

    if decision_gate.status == "PASS":
        next_action = "Review the canonical report before manually approving the next stage."
    elif decision_gate.status == "FAIL":
        next_action = "Stop progression and correct the integrity failure before any provider call."
    else:
        next_action = "Keep the campaign on hold until the reported coverage and stage requirements are met."

    return {
        "schema_version": "3.0",
        "app_version": APP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan_id": plan.get("plan_id"),
        "plan_request_id": plan.get("plan_request_id"),
        "campaign_id": campaign_plan.get("campaign_id"),
        "campaign_key": campaign_plan.get("campaign_key"),
        "baseline": baseline,
        "target_stage": resolved_target_stage,
        "backfill_status": state.get("status") or "not_run",
        "consumed_credits": total_credits,
        "credits": {
            "discovery_credits": discovery_credits,
            "snapshot_credits": snapshot_credits,
            "total_credits": total_credits,
            "maximum_credits": global_credit_cap,
            "remaining_credits": max(0, global_credit_cap - total_credits) if global_credit_cap else None,
        },
        "decision_gate": decision_gate.to_dict(),
        "quality_gate": decision_gate.to_dict(),
        "gates": {
            "technical_integrity": integrity_gate,
            "provider_coverage": provider_gate,
            "result_matching": matching_gate,
            "consensus": consensus_gate,
            "winamax": winamax_gate,
            "selected_baseline": selected_baseline_gate,
            "statistical_evidence": statistical_gate,
        },
        "funnel": {
            "discovered_events": discovered_events,
            "requested_events": requested_events,
            "selected_events": selected_events,
            "not_selected_sample_limit": max(0, discovered_events - requested_events),
            "not_selected_budget_limit": max(0, requested_events - selected_events),
            "planned_requests": planned_requests,
            "completed_requests": completed_requests,
            "planned_event_snapshots": planned_event_snapshots,
            "completed_event_snapshots": completed_event_snapshots,
            "provider_returned_event_snapshots": returned_event_snapshots,
            "accepted_event_snapshots": accepted_event_snapshots,
            "accepted_events": accepted_events,
            "reliably_matched_events": matched_total,
            "consensus_ready_event_snapshots": consensus_ready,
            "winamax_ready_event_snapshots": winamax_ready,
            "consensus_ready_events": len(consensus_ready_ids),
            "winamax_ready_events": len(winamax_ready_ids),
            "benchmark_ready_events": benchmark_ready_events,
            "benchmark_ready_events_by_baseline": benchmark_ready_events_by_baseline,
        },
        "counts": {
            "planned_events": selected_events,
            "discovered_events": discovered_events,
            "requested_events": requested_events,
            "selected_events": selected_events,
            "events_with_odds": accepted_events,
            "benchmark_ready_events": benchmark_ready_events,
            "historical_odds_rows": total_rows,
            "accepted_rows": accepted_rows,
            "quarantined_temporal_rows": int(len(temporal_issues)),
            "duplicate_rows": duplicate_rows,
            "matching_collisions": matching_collisions,
            "bookmakers": len(requested_bookmakers),
            "winamax_events": winamax_ready,
            "consensus_events": consensus_ready,
        },
        "rates": {
            "event_coverage": provider_coverage_rate,
            "provider_return_coverage": provider_coverage_rate,
            "consensus_coverage": consensus_coverage_rate,
            "winamax_coverage": winamax_coverage_rate,
            "temporal_violation": temporal_violation_rate,
            "duplicate": duplicate_rate,
            "reliable_matching": matching_rate,
        },
        "bookmaker_coverage": bookmaker_coverage,
        "matching": matching,
        "event_outcome_counts": outcome_counts,
        "event_outcomes": ledger,
        "selection_status_source": selection_source,
        "blockers": list(dict.fromkeys(integrity_fail_reasons + hold_reasons)),
        "warnings": list(dict.fromkeys(warnings)),
        "benchmark": benchmark_summary,
        "next_action": next_action,
        "responsible_use": {
            "experimental_analysis": True,
            "profitability_claim": False,
            "stake_recommendation": False,
            "automatic_bet_placement": False,
        },
    }


def load_json(path: str | Path) -> dict[str, Any] | None:
    candidate = Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))
