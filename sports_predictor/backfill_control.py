from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


VALIDATION_EVENT_LIMIT = 30


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def dataframe_sha256(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    text = normalized.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_plan_identity(summary: Mapping[str, Any], requests: pd.DataFrame, targets: pd.DataFrame) -> dict[str, str]:
    request_hash = dataframe_sha256(requests)
    target_hash = dataframe_sha256(targets)
    identity_input = {
        "sport_keys": list(summary.get("sport_keys") or []),
        "markets": list(summary.get("markets") or []),
        "bookmakers": list(summary.get("bookmakers") or []),
        "estimated_credits": int(summary.get("estimated_credits") or 0),
        "request_count": int(len(requests)),
        "target_count": int(len(targets)),
        "requests_sha256": request_hash,
        "targets_sha256": target_hash,
    }
    plan_id = hashlib.sha256(_canonical_json(identity_input).encode("utf-8")).hexdigest()
    return {
        "plan_id": plan_id,
        "requests_sha256": request_hash,
        "targets_sha256": target_hash,
    }


def validate_plan_bundle(plan_dir: str | Path) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    directory = Path(plan_dir)
    summary = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
    requests = pd.read_csv(directory / "requests.csv")
    targets = pd.read_csv(directory / "targets.csv")
    identity = build_plan_identity(summary, requests, targets)
    for key, actual in identity.items():
        expected = summary.get(key)
        if not expected or str(expected) != str(actual):
            raise RuntimeError(f"Historical backfill plan integrity mismatch: {key}")
    return summary, requests, targets


@dataclass(frozen=True)
class ExecutionGate:
    allowed: bool
    mode: str
    reason: str
    approval_required: bool


def execution_gate(
    summary: Mapping[str, Any],
    *,
    max_credits: int,
    approval_plan_id: str | None = None,
) -> ExecutionGate:
    estimated = int(summary.get("estimated_credits") or 0)
    event_count = int(summary.get("event_count") or 0)
    plan_id = str(summary.get("plan_id") or "")
    mode = "validation" if event_count <= VALIDATION_EVENT_LIMIT else "full"
    if estimated > int(max_credits):
        return ExecutionGate(False, mode, f"estimated credits {estimated} exceed cap {max_credits}", mode == "full")
    if mode == "full" and approval_plan_id != plan_id:
        return ExecutionGate(False, mode, "full backfill requires exact --approve-plan PLAN_ID", True)
    return ExecutionGate(True, mode, "approved within immutable credit cap", mode == "full")
