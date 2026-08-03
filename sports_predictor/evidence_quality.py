from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


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
    statuses = {"exact": 0, "high_confidence": 0, "manual_review": 0, "rejected": 0}
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
        else:
            statuses["rejected"] += 1
    return statuses


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
) -> tuple[list[dict[str, Any]], int, int, int]:
    target_keys = _target_key_frame(targets)
    if target_keys.empty:
        target_keys = _target_key_frame(clean, snapshot_column="requested_snapshot_at")
    denominator = int(len(target_keys))
    complete = _complete_h2h_markets(clean)
    complete = complete[complete["complete"]] if not complete.empty else complete
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
        return rows, denominator, 0, 0
    grouped = complete.groupby(["event_id", "snapshot_key"], dropna=False)["bookmaker_key"].nunique()
    consensus_ready = int((grouped >= 2).sum())
    winamax_ready = int(
        complete.loc[complete["bookmaker_key"].astype(str).eq("winamax_fr"), ["event_id", "snapshot_key"]]
        .drop_duplicates()
        .shape[0]
    )
    return rows, denominator, consensus_ready, winamax_ready


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
) -> dict[str, Any]:
    """Build a V3.9 evidence report with explicit, non-overlapping denominators.

    Discovered events are never treated as provider failures merely because the
    immutable credit cap prevented them from being selected.  Provider coverage
    is calculated only over event snapshots that the backfill actually planned
    and completed.
    """

    plan = dict(plan or {})
    state = dict(state or {})
    events = events.copy() if events is not None else pd.DataFrame()
    requests = requests.copy() if requests is not None else pd.DataFrame()
    targets = targets.copy() if targets is not None else pd.DataFrame()
    clean, temporal_issues = temporal_row_audit(odds_rows) if not odds_rows.empty else (odds_rows.copy(), pd.DataFrame())

    duplicate_columns = [
        column
        for column in ("event_id", "bookmaker_key", "market_key", "outcome_name", "requested_snapshot_at")
        if column in odds_rows.columns
    ]
    duplicate_mask = odds_rows.duplicated(duplicate_columns, keep=False) if duplicate_columns else pd.Series(False, index=odds_rows.index)
    duplicate_rows = int(odds_rows.duplicated(duplicate_columns).sum()) if duplicate_columns else 0
    total_rows = int(len(odds_rows))
    accepted_rows = int(len(clean))

    discovered_event_ids = _unique_event_ids(events)
    selected_event_ids = _unique_event_ids(targets)
    if not selected_event_ids:
        selected_event_ids = _unique_event_ids(clean)
    returned_event_ids = _unique_event_ids(clean)

    discovered_events = len(discovered_event_ids) or _safe_int((discovery_state or {}).get("event_count"))
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
    returned_event_snapshots = int(len(returned_keys))
    accepted_event_snapshots = returned_event_snapshots
    accepted_events = len(returned_event_ids)

    requested_bookmakers = [str(value) for value in plan.get("bookmakers") or []]
    if not requested_bookmakers and "bookmaker_key" in clean.columns:
        requested_bookmakers = sorted(clean["bookmaker_key"].dropna().astype(str).unique().tolist())
    bookmaker_coverage, bookmaker_denominator, consensus_ready, winamax_ready = _bookmaker_coverage(
        clean,
        targets=completed_target_keys,
        requested_bookmakers=requested_bookmakers,
    )

    matching = _matching_counts(matches, returned_event_ids if returned_event_ids else None)
    matched_total = matching["exact"] + matching["high_confidence"]
    matching_denominator = sum(matching.values())
    matching_rate = matched_total / matching_denominator if matching_denominator else None

    temporal_violation_rate = len(temporal_issues) / total_rows if total_rows else 0.0
    duplicate_rate = duplicate_rows / total_rows if total_rows else 0.0
    provider_coverage_rate = returned_event_snapshots / completed_event_snapshots if completed_event_snapshots else 0.0
    consensus_coverage_rate = consensus_ready / bookmaker_denominator if bookmaker_denominator else 0.0
    winamax_coverage_rate = winamax_ready / bookmaker_denominator if bookmaker_denominator else 0.0

    integrity_reasons: list[str] = []
    if total_rows == 0:
        integrity_reasons.append("no_historical_odds_rows")
    if temporal_violation_rate > 0:
        integrity_reasons.append("temporal_violations_detected")
    if duplicate_rate > 0.01:
        integrity_reasons.append("duplicate_rate_above_1_percent")
    if state and str(state.get("status") or "") != "completed":
        integrity_reasons.append("backfill_not_completed")
    max_credits = _safe_int(plan.get("max_credits"), 0)
    if max_credits and _safe_int(state.get("consumed_credits")) > max_credits:
        integrity_reasons.append("credit_cap_exceeded")
    integrity_gate = (
        _gate("blocked", integrity_reasons[0], False)
        if integrity_reasons
        else _gate("passed", "temporal, duplicate and budget controls passed", True)
    )

    if completed_event_snapshots == 0:
        provider_gate = _gate("not_evaluable", "no completed provider target exists", False)
    elif provider_coverage_rate < 0.95:
        provider_gate = _gate("blocked", "provider_return_rate_below_95_percent", False)
    else:
        provider_gate = _gate("passed", "provider coverage is calculated only on completed targets", True)

    if matches is None or matches.empty:
        matching_gate = _gate("not_evaluated", "result matching was not available for this report", True)
    elif matching_denominator == 0:
        matching_gate = _gate("not_evaluable", "no returned event was eligible for result matching", False)
    elif matching_rate is not None and matching_rate < 0.95:
        matching_gate = _gate("blocked", "reliable_matching_below_95_percent", False)
    else:
        matching_gate = _gate("passed", "reliable matching passed on returned events", True)

    if bookmaker_denominator == 0:
        consensus_gate = _gate("not_evaluable", "no complete market target is available", False)
        winamax_gate = _gate("not_evaluable", "no complete market target is available", False)
    else:
        consensus_gate = (
            _gate("available", "at least two complete bookmakers cover most completed targets", True)
            if consensus_coverage_rate >= 0.70
            else _gate("insufficient", "consensus_coverage_below_70_percent", False)
        )
        winamax_gate = (
            _gate("available", "Winamax coverage is sufficient for a dedicated comparison", True)
            if winamax_coverage_rate >= 0.70
            else _gate("insufficient", "winamax_coverage_below_70_percent", False)
        )

    if accepted_events < 30:
        statistical_gate = _gate("technical_validation", "fewer than 30 accepted events; no statistical conclusion", False)
    elif accepted_events < 100:
        statistical_gate = _gate("pipeline_validation", "30 to 99 accepted events; pipeline validation only", False)
    elif accepted_events < 300:
        statistical_gate = _gate("exploratory", "100 to 299 accepted events; exploratory evidence only", False)
    elif accepted_events < 1000:
        statistical_gate = _gate("preliminary", "300 to 999 accepted events; preliminary analysis only", False)
    else:
        statistical_gate = _gate("analysis_ready", "at least 1000 accepted events", True)

    blockers: list[str] = []
    warnings: list[str] = []
    blockers.extend(integrity_reasons)
    if provider_gate["status"] == "blocked":
        blockers.append(str(provider_gate["reason"]))
    if matching_gate["status"] == "blocked":
        blockers.append(str(matching_gate["reason"]))
    if duplicate_rows and duplicate_rate <= 0.01:
        warnings.append("duplicate_rows_present")
    if consensus_gate["status"] == "insufficient":
        warnings.append("consensus_coverage_below_70_percent")
    if winamax_gate["status"] == "insufficient":
        warnings.append("winamax_coverage_below_70_percent")
    if statistical_gate["status"] != "analysis_ready":
        warnings.append(str(statistical_gate["reason"]).replace(" ", "_"))

    if blockers:
        overall_gate = QualityGate("blocked", blockers[0], False)
    elif accepted_events < 30:
        overall_gate = QualityGate("technical_validation", "pipeline validated on a very small accepted sample", True)
    elif accepted_events < 100:
        overall_gate = QualityGate("pipeline_validation", "pipeline passed; sample remains too small for inference", True)
    elif accepted_events < 1000:
        overall_gate = QualityGate("exploratory", "data quality passed; statistical evidence remains preliminary", True)
    else:
        overall_gate = QualityGate("analysis_ready", "quality gates passed for a first serious statistical analysis", True)

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

    next_action = "Recompute the latest evidence from the GitHub artifact; this consumes zero provider credits."
    if not blockers and accepted_events < 30:
        next_action = "Keep this run as a technical validation; do not infer model performance from it."
    elif not blockers and consensus_gate["accepted"]:
        next_action = "Review the consensus benchmark before approving any larger capped sample."

    return {
        "schema_version": "2.0",
        "app_version": "4.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan_id": plan.get("plan_id"),
        "plan_request_id": plan.get("plan_request_id"),
        "backfill_status": state.get("status") or "not_run",
        "consumed_credits": _safe_int(state.get("consumed_credits")),
        "quality_gate": overall_gate.to_dict(),
        "gates": {
            "technical_integrity": integrity_gate,
            "provider_coverage": provider_gate,
            "result_matching": matching_gate,
            "consensus": consensus_gate,
            "winamax": winamax_gate,
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
        },
        "counts": {
            # Backward-compatible keys now use the correct selected-target denominator.
            "planned_events": selected_events,
            "discovered_events": discovered_events,
            "requested_events": requested_events,
            "selected_events": selected_events,
            "events_with_odds": accepted_events,
            "historical_odds_rows": total_rows,
            "accepted_rows": accepted_rows,
            "quarantined_temporal_rows": int(len(temporal_issues)),
            "duplicate_rows": duplicate_rows,
            "bookmakers": len(requested_bookmakers),
            "winamax_events": winamax_ready,
            "consensus_events": consensus_ready,
        },
        "rates": {
            # event_coverage is retained for the V3.8 frontend but corrected.
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
        "blockers": list(dict.fromkeys(blockers)),
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
