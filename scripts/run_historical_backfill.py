from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig
from sports_predictor.database import init_database, persist_odds_rows, update_backfill_job
from sports_predictor.odds_data import normalize_odds_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a resumable historical odds backfill plan.")
    parser.add_argument("--plan-dir", default="data/odds_api/backfill")
    parser.add_argument("--max-credits", type=int, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan_dir = ROOT / args.plan_dir
    summary = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
    requests = pd.read_csv(plan_dir / "requests.csv")
    targets = pd.read_csv(plan_dir / "targets.csv")
    estimated = int(summary["estimated_credits"])
    if estimated > int(args.max_credits):
        print(f"ABORT: plan estimates {estimated} credits, cap is {args.max_credits}")
        return 3
    if not args.execute:
        print(json.dumps({**summary, "execution": False}, indent=2))
        print("DRY-RUN only. Add --execute to consume credits.")
        return 0

    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    chunks = plan_dir / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    state_path = plan_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"completed": [], "consumed_credits": 0}
    completed = set(int(x) for x in state.get("completed", []))
    consumed = int(state.get("consumed_credits", 0))
    per_request_cost = int(estimated / max(1, len(requests)))
    if args.job_id:
        update_backfill_job(args.job_id, status="running", completed_requests=len(completed), consumed_credits=consumed)

    try:
        for request in requests.to_dict(orient="records"):
            number = int(request["request_number"])
            if number in completed:
                continue
            if consumed + per_request_cost > args.max_credits:
                raise RuntimeError("credit cap reached before next request")
            snapshot = pd.to_datetime(request["snapshot_at"], utc=True, errors="raise").isoformat().replace("+00:00", "Z")
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
                & pd.to_datetime(targets["snapshot_at"], utc=True).eq(pd.to_datetime(request["snapshot_at"], utc=True))
            ][["event_id", "stage"]]
            if not rows.empty:
                rows["requested_snapshot_at"] = pd.to_datetime(request["snapshot_at"], utc=True)
                rows = rows.merge(request_targets, on="event_id", how="inner")
                rows.to_csv(chunks / f"{number:06d}.csv", index=False)
                persist_odds_rows(
                    rows,
                    fetched_at=response.fetched_at,
                    quota_remaining=response.quota.remaining,
                    quota_last_cost=response.quota.last_cost,
                    job_name="historical_backfill",
                    sport_key=str(request["sport_key"]),
                )
            consumed += 0 if response.from_cache else int(response.quota.last_cost or per_request_cost)
            completed.add(number)
            state = {"completed": sorted(completed), "consumed_credits": consumed, "last_request": number}
            temporary = state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
            temporary.replace(state_path)
            if args.job_id:
                update_backfill_job(args.job_id, completed_requests=len(completed), consumed_credits=consumed)
            print(f"{len(completed)}/{len(requests)} · request={number} · rows={len(rows)} · consumed={consumed}")
        frames = [pd.read_csv(path) for path in sorted(chunks.glob("*.csv"))]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        combined.to_csv(plan_dir / "historical_odds_long.csv", index=False)
        if args.job_id:
            update_backfill_job(args.job_id, status="completed", completed_requests=len(completed), consumed_credits=consumed)
        print(json.dumps({"status": "completed", "requests": len(completed), "rows": len(combined), "consumed_credits": consumed}, indent=2))
        return 0
    except Exception as exc:
        if args.job_id:
            update_backfill_job(args.job_id, status="failed", completed_requests=len(completed), consumed_credits=consumed, error_message=str(exc)[:1000])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
