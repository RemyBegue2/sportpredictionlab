from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from .version import APP_VERSION

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
PROVIDER_MIN_COVERAGE = 0.80
MATCHING_MIN_COVERAGE = 0.95
BASELINE_MIN_COVERAGE = 0.70


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


def next_stage(stage: int | None) -> int | None:
    if stage is None:
        return CAMPAIGN_STAGES[0]
    stage = normalized_stage(stage)
    index = CAMPAIGN_STAGES.index(stage)
    if index + 1 >= len(CAMPAIGN_STAGES):
        return None
    return CAMPAIGN_STAGES[index + 1]


def estimate_snapshot_cost(previous_evidence: Mapping[str, Any] | None) -> float:
    credits = (previous_evidence or {}).get("credits") or {}
    consumed = _ratio(credits.get("snapshot_credits"))
    if consumed is None:
        consumed = _ratio((previous_evidence or {}).get("consumed_credits"))
    completed = _ratio(_nested(previous_evidence, "funnel", "completed_event_snapshots", default=None))
    if completed is None:
        completed = _ratio(_nested(previous_evidence, "counts", "events_with_odds", default=None))
    if consumed is None or completed is None or completed <= 0:
        return DEFAULT_SNAPSHOT_COST
    return max(1.0, min(50.0, consumed / completed))


def _benchmark_ready_count(previous_evidence: Mapping[str, Any] | None, *, baseline: str) -> int:
    if not previous_evidence:
        return 0
    funnel = previous_evidence.get("funnel") or {}
    by_baseline = funnel.get("benchmark_ready_events_by_baseline") or {}
    if baseline in by_baseline:
        return max(0, int(by_baseline.get(baseline) or 0))

    report_baseline = str(previous_evidence.get("baseline") or "")
    explicit = funnel.get("benchmark_ready_events")
    if explicit is not None and (not report_baseline or report_baseline == baseline):
        return max(0, int(explicit or 0))

    benchmark_rows = _nested(previous_evidence, "benchmark", "evaluated_rows", default=None)
    if benchmark_rows is not None and (not report_baseline or report_baseline == baseline):
        return max(0, int(benchmark_rows or 0))

    accepted = int(funnel.get("accepted_events") or (previous_evidence.get("counts") or {}).get("events_with_odds") or 0)
    matched = int(funnel.get("reliably_matched_events") or accepted)
    baseline_key = "consensus_ready_events" if baseline == "consensus" else "winamax_ready_events"
    legacy_key = "consensus_ready_event_snapshots" if baseline == "consensus" else "winamax_ready_event_snapshots"
    baseline_ready = int(funnel.get(baseline_key) or funnel.get(legacy_key) or 0)
    if baseline_ready <= 0:
        return 0
    return max(0, min(accepted, matched, baseline_ready))


def evidence_stage(previous_evidence: Mapping[str, Any] | None, *, baseline: str = "consensus") -> int | None:
    if baseline not in BASELINES:
        raise ValueError(f"baseline must be one of {list(BASELINES)}")
    completed = _benchmark_ready_count(previous_evidence, baseline=baseline)
    eligible = [stage for stage in CAMPAIGN_STAGES if completed >= stage]
    return max(eligible) if eligible else None


def evaluate_scale_gate(
    previous_evidence: Mapping[str, Any] | None,
    *,
    baseline: str = "consensus",
) -> dict[str, Any]:
    if baseline not in BASELINES:
        raise ValueError(f"baseline must be one of {list(BASELINES)}")
    if not previous_evidence:
        return {
            "status": "HOLD",
            "accepted": False,
            "reason": "no_previous_evidence",
            "baseline": baseline,
            "checks": {},
            "completed_stage": None,
        }

    rates = previous_evidence.get("rates") or {}
    counts = previous_evidence.get("counts") or {}
    gates = previous_evidence.get("gates") or {}
    provider = _ratio(rates.get("provider_return_coverage"))
    matching = _ratio(rates.get("reliable_matching"))
    baseline_rate = _ratio(rates.get(f"{baseline}_coverage"))
    temporal = int(counts.get("quarantined_temporal_rows") or 0)
    duplicates = int(counts.get("duplicate_rows") or 0)
    matching_collisions = int(counts.get("matching_collisions") or 0)

    technical_gate = gates.get("technical_integrity") or {}
    technical_status = str(technical_gate.get("status") or "")
    if technical_gate and not technical_status:
        technical_status = "PASS" if bool(technical_gate.get("accepted")) else "HOLD"
    technical_ok = technical_status == "PASS" if technical_gate else (
        temporal == 0 and duplicates == 0 and matching_collisions == 0
    )
    checks = {
        "technical_integrity": technical_ok,
        "temporal_violations_zero": temporal == 0,
        "duplicates_zero": duplicates == 0,
        "matching_collisions_zero": matching_collisions == 0,
        f"provider_return_coverage_at_least_{int(PROVIDER_MIN_COVERAGE * 100)}_percent": (
            provider is not None and provider >= PROVIDER_MIN_COVERAGE
        ),
        f"reliable_matching_at_least_{int(MATCHING_MIN_COVERAGE * 100)}_percent": (
            matching is not None and matching >= MATCHING_MIN_COVERAGE
        ),
        f"{baseline}_coverage_at_least_{int(BASELINE_MIN_COVERAGE * 100)}_percent": (
            baseline_rate is not None and baseline_rate >= BASELINE_MIN_COVERAGE
        ),
    }
    failed = [name for name, ok in checks.items() if not ok]
    integrity_failed = technical_status == "FAIL" or any(
        not checks[name]
        for name in ("temporal_violations_zero", "duplicates_zero", "matching_collisions_zero")
    )
    status = "PASS" if not failed else ("FAIL" if integrity_failed else "HOLD")
    return {
        "status": status,
        "accepted": status == "PASS",
        "reason": "all_scale_checks_passed" if not failed else "failed:" + ",".join(failed),
        "baseline": baseline,
        "checks": checks,
        "completed_stage": evidence_stage(previous_evidence, baseline=baseline),
        "benchmark_ready_events": _benchmark_ready_count(previous_evidence, baseline=baseline),
        "observed": {
            "provider_return_coverage": provider,
            "reliable_matching": matching,
            f"{baseline}_coverage": baseline_rate,
            "temporal_violations": temporal,
            "duplicate_rows": duplicates,
            "matching_collisions": matching_collisions,
        },
    }


def _source_commit() -> str:
    return (
        os.getenv("SOURCE_COMMIT")
        or os.getenv("GITHUB_SHA")
        or os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or "unknown"
    ).strip() or "unknown"


@dataclass(frozen=True)
class CampaignPlan:
    schema_version: str
    app_version: str
    campaign_id: str
    campaign_key: str
    source_commit: str
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
    current_campaign: Mapping[str, Any] | None = None,
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
    app_version: str = APP_VERSION,
    source_commit: str | None = None,
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

    previous_stage = evidence_stage(previous_evidence, baseline=baseline)
    gate = evaluate_scale_gate(previous_evidence, baseline=baseline)
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
    elif estimated_events < stage:
        execution_allowed = False
        reason = "budget_cannot_fund_complete_target_stage"
    elif mode == "start_next_stage":
        expected = next_stage(previous_stage)
        if expected is None:
            execution_allowed = False
            reason = "campaign_already_completed_at_stage_1000"
        elif stage != expected:
            execution_allowed = False
            reason = f"target_stage_must_equal_next_stage_{expected}"
        elif stage > CAMPAIGN_STAGES[0] and not gate["accepted"]:
            execution_allowed = False
            reason = "previous_stage_quality_gate_failed"
    elif mode == "continue_current_stage":
        current = dict(current_campaign or {})
        required_match = {
            "target_stage": stage,
            "baseline": baseline,
            "max_credits": max_credits,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        if not current:
            execution_allowed = False
            reason = "no_existing_campaign_to_continue"
        elif any(current.get(key) != value for key, value in required_match.items()):
            execution_allowed = False
            reason = "continue_parameters_must_match_existing_campaign"
        elif str(current.get("app_version") or app_version) != app_version:
            execution_allowed = False
            reason = "checkpoint_app_version_mismatch"
        elif previous_stage is not None and stage <= previous_stage:
            execution_allowed = False
            reason = "current_stage_already_completed_use_start_next_stage"

    stable_identity = {
        "schema_version": "2.0",
        "app_version": app_version,
        "target_stage": stage,
        "baseline": baseline,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "max_credits": max_credits,
    }
    campaign_key = "CPK-" + hashlib.sha256(_canonical_json(stable_identity).encode("utf-8")).hexdigest()[:24].upper()
    run_identity = {
        **stable_identity,
        "mode": mode,
        "estimated_discovery_calls": discovery_calls,
        "estimated_snapshot_cost": round(snapshot_cost, 6),
        "previous_completed_stage": previous_stage,
        "scale_gate": gate,
    }
    campaign_id = "CMP-" + hashlib.sha256(_canonical_json(run_identity).encode("utf-8")).hexdigest()[:24].upper()

    return CampaignPlan(
        schema_version="2.0",
        app_version=app_version,
        campaign_id=campaign_id,
        campaign_key=campaign_key,
        source_commit=source_commit or _source_commit(),
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
