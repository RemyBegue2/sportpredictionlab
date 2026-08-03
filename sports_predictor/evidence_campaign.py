from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

CAMPAIGN_STAGES: tuple[int, ...] = (30, 100, 300, 1000)
CAMPAIGN_MODES: tuple[str, ...] = (
    "dry_run",
    "continue_current_stage",
    "start_next_stage",
    "recompute_only",
)
BASELINES: tuple[str, ...] = ("consensus", "winamax")
DEFAULT_START_DATE = "2023-01-01"
DEFAULT_SNAPSHOT_COST = 10.0


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _ratio(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _nested(mapping: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    current: Any = mapping or {}
    for key in keys:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key)
    return default if current is None else current


def normalized_stage(value: int | str) -> int:
    stage = int(value)
    if stage not in CAMPAIGN_STAGES:
        raise ValueError(f"target_stage must be one of {list(CAMPAIGN_STAGES)}")
    return stage


def next_stage(stage: int | None) -> int:
    if stage is None:
        return CAMPAIGN_STAGES[0]
    stage = normalized_stage(stage)
    index = CAMPAIGN_STAGES.index(stage)
    if index + 1 >= len(CAMPAIGN_STAGES):
        return stage
    return CAMPAIGN_STAGES[index + 1]


def estimate_snapshot_cost(previous_evidence: Mapping[str, Any] | None) -> float:
    consumed = _ratio((previous_evidence or {}).get("consumed_credits"))
    completed = _ratio(
        _nested(previous_evidence, "funnel", "completed_event_snapshots", default=None)
    )
    if completed is None:
        completed = _ratio(_nested(previous_evidence, "counts", "events_with_odds", default=None))
    if consumed is None or completed is None or completed <= 0:
        return DEFAULT_SNAPSHOT_COST
    return max(1.0, min(50.0, consumed / completed))


def evidence_stage(previous_evidence: Mapping[str, Any] | None) -> int | None:
    if not previous_evidence:
        return None
    completed = int(
        _nested(previous_evidence, "funnel", "completed_event_snapshots", default=0)
        or _nested(previous_evidence, "counts", "events_with_odds", default=0)
        or 0
    )
    eligible = [stage for stage in CAMPAIGN_STAGES if completed >= stage]
    return max(eligible) if eligible else None


def evaluate_scale_gate(previous_evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    if not previous_evidence:
        return {
            "accepted": False,
            "reason": "no_previous_evidence",
            "checks": {},
        }

    rates = previous_evidence.get("rates") or {}
    counts = previous_evidence.get("counts") or {}
    gates = previous_evidence.get("gates") or {}
    provider = _ratio(rates.get("provider_return_coverage"))
    matching = _ratio(rates.get("reliable_matching"))
    consensus = _ratio(rates.get("consensus_coverage"))
    temporal = int(counts.get("quarantined_temporal_rows") or 0)
    duplicates = int(counts.get("duplicate_rows") or 0)

    technical_gate = gates.get("technical_integrity") or {}
    technical_ok = bool(technical_gate.get("accepted")) if technical_gate else temporal == 0 and duplicates == 0
    checks = {
        "technical_integrity": technical_ok,
        "temporal_violations_zero": temporal == 0,
        "duplicates_zero": duplicates == 0,
        "provider_return_coverage_at_least_80_percent": provider is not None and provider >= 0.80,
        "reliable_matching_at_least_95_percent": matching is not None and matching >= 0.95,
        "consensus_coverage_at_least_70_percent": consensus is not None and consensus >= 0.70,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "accepted": not failed,
        "reason": "all_scale_checks_passed" if not failed else "failed:" + ",".join(failed),
        "checks": checks,
        "observed": {
            "provider_return_coverage": provider,
            "reliable_matching": matching,
            "consensus_coverage": consensus,
            "temporal_violations": temporal,
            "duplicate_rows": duplicates,
        },
    }


@dataclass(frozen=True)
class CampaignPlan:
    schema_version: str
    app_version: str
    campaign_id: str
    generated_at: str
    mode: str
    target_stage: int
    baseline: str
    start_date: str
    end_date: str
    max_credits: int
    estimated_discovery_calls: int
    estimated_snapshot_cost: float
    estimated_snapshot_capacity: int
    estimated_events_this_run: int
    previous_completed_stage: int | None
    scale_gate: dict[str, Any]
    execution_allowed: bool
    execution_reason: str
    confirmation_required: str
    consumes_provider_credits: bool
    automatic_model_promotion: bool
    automatic_bet_placement: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_campaign_plan(
    *,
    mode: str,
    target_stage: int | str,
    max_credits: int,
    baseline: str,
    previous_evidence: Mapping[str, Any] | None = None,
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
    app_version: str = "4.0.0",
) -> CampaignPlan:
    if mode not in CAMPAIGN_MODES:
        raise ValueError(f"mode must be one of {list(CAMPAIGN_MODES)}")
    stage = normalized_stage(target_stage)
    if baseline not in BASELINES:
        raise ValueError(f"baseline must be one of {list(BASELINES)}")
    max_credits = int(max_credits)
    if max_credits < 0 or max_credits > 20000:
        raise ValueError("max_credits must be between 0 and 20000")

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date) if end_date else datetime.now(timezone.utc).date()
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    previous_stage = evidence_stage(previous_evidence)
    gate = evaluate_scale_gate(previous_evidence)
    discovery_calls = min(180, max(14, math.ceil(stage / 8)))
    snapshot_cost = estimate_snapshot_cost(previous_evidence)
    available_for_snapshots = max(0, max_credits - discovery_calls)
    snapshot_capacity = int(available_for_snapshots // snapshot_cost)
    estimated_events = min(stage, snapshot_capacity)

    execution_allowed = True
    reason = "approved"
    if mode == "dry_run":
        execution_allowed = False
        reason = "dry_run_never_calls_provider"
    elif mode == "recompute_only":
        execution_allowed = True
        reason = "recompute_only_uses_saved_data"
    elif max_credits <= discovery_calls:
        execution_allowed = False
        reason = "budget_does_not_leave_capacity_for_odds_snapshots"
    elif estimated_events <= 0:
        execution_allowed = False
        reason = "no_snapshot_capacity"
    elif mode == "start_next_stage":
        if estimated_events < stage:
            execution_allowed = False
            reason = "budget_cannot_fund_complete_target_stage"
        expected = next_stage(previous_stage)
        if execution_allowed and stage != expected:
            execution_allowed = False
            reason = f"target_stage_must_equal_next_stage_{expected}"
        elif execution_allowed and stage > CAMPAIGN_STAGES[0] and not gate["accepted"]:
            execution_allowed = False
            reason = "previous_stage_quality_gate_failed"
    elif mode == "continue_current_stage":
        if previous_stage is not None and stage < previous_stage:
            execution_allowed = False
            reason = "target_stage_cannot_be_lower_than_completed_stage"

    identity = {
        "schema_version": "1.0",
        "mode": mode,
        "target_stage": stage,
        "baseline": baseline,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "max_credits": max_credits,
        "estimated_discovery_calls": discovery_calls,
        "estimated_snapshot_cost": round(snapshot_cost, 6),
        "previous_completed_stage": previous_stage,
        "scale_gate": gate,
    }
    campaign_id = "CMP-" + hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()[:24].upper()

    return CampaignPlan(
        schema_version="1.0",
        app_version=app_version,
        campaign_id=campaign_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        target_stage=stage,
        baseline=baseline,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        max_credits=max_credits,
        estimated_discovery_calls=discovery_calls,
        estimated_snapshot_cost=round(snapshot_cost, 4),
        estimated_snapshot_capacity=snapshot_capacity,
        estimated_events_this_run=estimated_events,
        previous_completed_stage=previous_stage,
        scale_gate=gate,
        execution_allowed=execution_allowed,
        execution_reason=reason,
        confirmation_required="EXECUTE_CAMPAIGN",
        consumes_provider_credits=mode not in {"dry_run", "recompute_only"},
        automatic_model_promotion=False,
        automatic_bet_placement=False,
    )


def load_json(path: str | Path) -> dict[str, Any] | None:
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
