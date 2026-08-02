from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.backfill_control import execution_gate, validate_plan_bundle
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig
from sports_predictor.database import init_database, persist_odds_rows, record_data_quality_issue, update_backfill_job
from sports_predictor.odds_data import normalize_odds_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute an immutable and resumable historical odds backfill plan.")
    parser.add_argument("--plan-dir", default="data/odds_api/backfill")
    parser.add_argument("--max-credits", type=int, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approve-plan", help="Required for full plans; must equal plan.json plan_id exactly.")
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args()


def _write_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    plan_dir = ROOT / args.plan_dir
    summary, requests, targets = validate_plan_bundle(plan_dir)
    gate = execution_gate(summary, max_credits=args.max_credits, approval_plan_id=args.approve_plan)
    if not gate.allowed:
        print(json.dumps({"status": "blocked", "mode": gate.mode, "reason": gate.reason, "plan_id": summary["plan_id"]}, indent=2))
        return 3
    if not args.execute:
        print(json.dumps({**summary, "execution": False, "gate": gate.__dict__}, indent=2))
        print("DRY-RUN only. Add --execute after reviewing the immutable plan and credit cap.")
        return 0

    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    chunks = plan_dir / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    state_path = plan_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "schema_version": "1.0",
        "plan_id": summary["plan_id"],
        "completed": [],
        "failed": [],
        "consumed_credits": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if state.get("plan_id") != summary["plan_id"]:
        raise RuntimeError("Checkpoint belongs to a different immutable plan")
    completed = set(int(x) for x in state.get("completed", []))
    consumed = int(state.get("consumed_credits", 0))
    estimated = int(summary["estimated_credits"])
    per_request_cost = max(1, int((estimated + max(1, len(requests)) - 1) / max(1, len(requests))))
    if args.job_id:
        update_backfill_job(args.job_id, status="running", completed_requests=len(completed), consumed_credits=consumed)

    try:
        for request in requests.to_dict(orient="records"):
            number = int(request["request_number"])
            if number in completed:
                continue
            if consumed + per_request_cost > int(args.max_credits):
                raise RuntimeError("credit cap reached before next request")
            snapshot = pd.to_datetime(request["snapshot_at"], utc=True, errors="raise", format="mixed").isoformat().replace("+00:00", "Z")
            try:
                response = client.historical_odds(
                    str(request["sport_key"]),
                    snapshot_at=snapshot,
                    markets=summary["markets"],
                    bookmakers=summary["bookmakers"],
                    force_refresh=args.force_refresh,
                )
                rows = normalize_odds_payload(response.payload)
                request_targets = targets[
                    targets["sport_key"].astype(str).eq(str(request["sport_key"]))
                    & pd.to_datetime(targets["snapshot_at"], utc=True, format="mixed").eq(pd.to_datetime(request["snapshot_at"], utc=True))
                ][["event_id", "stage"]]
                if not rows.empty:
                    rows["requested_snapshot_at"] = pd.to_datetime(request["snapshot_at"], utc=True)
                    rows = rows.merge(request_targets, on="event_id", how="inner")
                    chunk_path = chunks / f"{number:06d}.csv"
                    rows.to_csv(chunk_path, index=False)
                    chunk_hash = hashlib.sha256(chunk_path.read_bytes()).hexdigest()
                    persist_odds_rows(
                        rows,
                        fetched_at=response.fetched_at,
                        quota_remaining=response.quota.remaining,
                        quota_last_cost=response.quota.last_cost,
                        job_name="historical_backfill",
                        sport_key=str(request["sport_key"]),
                    )
                else:
                    chunk_hash = None
                actual_cost = 0 if response.from_cache else int(response.quota.last_cost or per_request_cost)
                if actual_cost < 0:
                    raise RuntimeError("provider returned an invalid negative quota cost")
                consumed += actual_cost
                if consumed > int(args.max_credits):
                    raise RuntimeError("provider-reported cost exceeded immutable credit cap")
                completed.add(number)
                state.update({
                    "completed": sorted(completed),
                    "consumed_credits": consumed,
                    "last_request": number,
                    "last_chunk_sha256": chunk_hash,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                _write_state(state_path, state)
                if args.job_id:
                    update_backfill_job(args.job_id, completed_requests=len(completed), consumed_credits=consumed)
                print(f"{len(completed)}/{len(requests)} · request={number} · rows={len(rows)} · consumed={consumed}")
            except Exception as exc:
                failure = {
                    "request_number": number,
                    "sport_key": str(request["sport_key"]),
                    "snapshot_at": snapshot,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "at": datetime.now(timezone.utc).isoformat(),
                }
                state.setdefault("failed", []).append(failure)
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                _write_state(state_path, state)
                record_data_quality_issue(
                    issue_type="historical_backfill_request_failed",
                    severity="high",
                    provider_event_id=None,
                    details={**failure, "plan_id": summary["plan_id"]},
                )
                raise

        frames = [pd.read_csv(path) for path in sorted(chunks.glob("*.csv"))]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        combined.to_csv(plan_dir / "historical_odds_long.csv", index=False)
        state["status"] = "completed"
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_state(state_path, state)
        if args.job_id:
            update_backfill_job(args.job_id, status="completed", completed_requests=len(completed), consumed_credits=consumed)
        print(json.dumps({"status": "completed", "plan_id": summary["plan_id"], "requests": len(completed), "rows": len(combined), "consumed_credits": consumed}, indent=2))
        return 0
    except Exception as exc:
        if args.job_id:
            update_backfill_job(args.job_id, status="failed", completed_requests=len(completed), consumed_credits=consumed, error_message=str(exc)[:1000])
        print(traceback.format_exc())
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
