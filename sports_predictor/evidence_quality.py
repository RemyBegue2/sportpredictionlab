from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

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
        return frame.copy(), pd.DataFrame(columns=["row_index", "issues"])
    required = {"event_id", "commence_time", "requested_snapshot_at"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing temporal columns: {sorted(missing)}")
    work = frame.copy()
    work["commence_time"] = pd.to_datetime(work["commence_time"], utc=True, errors="coerce", format="mixed")
    work["requested_snapshot_at"] = pd.to_datetime(work["requested_snapshot_at"], utc=True, errors="coerce", format="mixed")
    issues: list[dict[str, Any]] = []
    valid_mask = []
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
            issues.append({"row_index": int(index) if isinstance(index, int) else str(index), "event_id": row.get("event_id"), "issues": row_issues})
    return work.loc[valid_mask].copy(), pd.DataFrame(issues)


def _matching_counts(matches: pd.DataFrame | None) -> dict[str, int]:
    statuses = {"exact": 0, "high_confidence": 0, "manual_review": 0, "rejected": 0}
    if matches is None or matches.empty:
        return statuses
    for row in matches.to_dict(orient="records"):
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


def build_evidence_quality_report(
    *,
    plan: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    odds_rows: pd.DataFrame,
    events: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
    benchmark: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    events = events.copy() if events is not None else pd.DataFrame()
    clean, temporal_issues = temporal_row_audit(odds_rows) if not odds_rows.empty else (odds_rows.copy(), pd.DataFrame())
    total_rows = int(len(odds_rows))
    accepted_rows = int(len(clean))
    duplicate_columns = [column for column in ("event_id", "bookmaker_key", "market_key", "outcome_name", "requested_snapshot_at") if column in odds_rows.columns]
    duplicate_rows = int(odds_rows.duplicated(duplicate_columns).sum()) if duplicate_columns else 0
    event_count = int(events["event_id"].nunique()) if "event_id" in events.columns else int(odds_rows["event_id"].nunique()) if "event_id" in odds_rows.columns else 0
    odds_event_count = int(clean["event_id"].nunique()) if "event_id" in clean.columns else 0
    winamax_events = int(clean.loc[clean.get("bookmaker_key", pd.Series(index=clean.index, dtype=str)).astype(str).eq("winamax_fr"), "event_id"].nunique()) if "event_id" in clean.columns else 0
    bookmaker_count = int(clean["bookmaker_key"].nunique()) if "bookmaker_key" in clean.columns else 0
    matching = _matching_counts(matches)
    matched_total = matching["exact"] + matching["high_confidence"]
    matching_denominator = sum(matching.values())
    matching_rate = matched_total / matching_denominator if matching_denominator else None
    temporal_violation_rate = len(temporal_issues) / total_rows if total_rows else 0.0
    duplicate_rate = duplicate_rows / total_rows if total_rows else 0.0
    coverage_rate = odds_event_count / event_count if event_count else 0.0
    winamax_coverage_rate = winamax_events / event_count if event_count else 0.0

    blockers: list[str] = []
    warnings: list[str] = []
    if total_rows == 0:
        blockers.append("no_historical_odds_rows")
    if temporal_violation_rate > 0:
        blockers.append("temporal_violations_detected")
    if duplicate_rate > 0.01:
        blockers.append("duplicate_rate_above_1_percent")
    elif duplicate_rows:
        warnings.append("duplicate_rows_present")
    if event_count and coverage_rate < 0.95:
        blockers.append("event_coverage_below_95_percent")
    if event_count and winamax_coverage_rate < 0.70:
        warnings.append("winamax_coverage_below_70_percent")
    if matching_rate is not None and matching_rate < 0.95:
        blockers.append("reliable_matching_below_95_percent")
    if state and str(state.get("status") or "") != "completed":
        blockers.append("backfill_not_completed")
    if plan and int((state or {}).get("consumed_credits") or 0) > int(plan.get("max_credits") or 0):
        blockers.append("credit_cap_exceeded")

    if blockers:
        gate = QualityGate("blocked", blockers[0], False)
    elif total_rows < 100:
        gate = QualityGate("technical_validation", "sample validates the pipeline but is too small for a performance claim", True)
    elif total_rows < 1000:
        gate = QualityGate("exploratory", "data quality passed; statistical evidence remains preliminary", True)
    else:
        gate = QualityGate("analysis_ready", "quality gates passed for a first serious statistical analysis", True)

    benchmark_summary = None
    if benchmark:
        benchmark_summary = {
            "evaluated_rows": int(benchmark.get("evaluated_rows") or 0),
            "verdict": benchmark.get("verdict"),
            "comparisons": benchmark.get("comparisons"),
            "closing_line_value": benchmark.get("closing_line_value"),
        }
    return {
        "schema_version": "1.0",
        "app_version": "3.8.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan_id": (plan or {}).get("plan_id"),
        "plan_request_id": (plan or {}).get("plan_request_id"),
        "backfill_status": (state or {}).get("status") or "not_run",
        "consumed_credits": int((state or {}).get("consumed_credits") or 0),
        "quality_gate": gate.to_dict(),
        "counts": {
            "planned_events": event_count,
            "events_with_odds": odds_event_count,
            "historical_odds_rows": total_rows,
            "accepted_rows": accepted_rows,
            "quarantined_temporal_rows": int(len(temporal_issues)),
            "duplicate_rows": duplicate_rows,
            "bookmakers": bookmaker_count,
            "winamax_events": winamax_events,
        },
        "rates": {
            "event_coverage": coverage_rate,
            "winamax_coverage": winamax_coverage_rate,
            "temporal_violation": temporal_violation_rate,
            "duplicate": duplicate_rate,
            "reliable_matching": matching_rate,
        },
        "matching": matching,
        "blockers": blockers,
        "warnings": warnings,
        "benchmark": benchmark_summary,
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
