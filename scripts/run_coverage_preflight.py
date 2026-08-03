from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.coverage_preflight import (
    DEFAULT_BOOKMAKERS,
    PREFLIGHT_BASELINES,
    build_coverage_preflight_report,
)
from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig
from sports_predictor.odds_data import normalize_odds_payload
from sports_predictor.version import APP_VERSION


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _evenly_spaced(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    if count >= len(frame):
        return frame.copy()
    if count <= 1:
        return frame.head(1).copy()
    positions = [round(index * (len(frame) - 1) / (count - 1)) for index in range(count)]
    positions = sorted(set(positions))
    cursor = 0
    while len(positions) < count:
        if cursor not in positions:
            positions.append(cursor)
        cursor += 1
    return frame.iloc[sorted(positions[:count])].copy()




def _stratified_quarter_sample(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    """Probe a few chronologically separated quarters without using results or model outputs."""
    if count >= len(frame):
        return frame.copy()
    work = frame.copy()
    work["_quarter"] = work["commence_time"].dt.tz_convert(None).dt.to_period("Q").astype(str)
    quarters = sorted(work["_quarter"].unique().tolist())
    period_count = min(len(quarters), max(1, count // 3))
    quarter_frame = pd.DataFrame({"quarter": quarters})
    chosen_quarters = _evenly_spaced(quarter_frame, period_count)["quarter"].tolist()
    base = count // period_count
    remainder = count % period_count
    pieces: list[pd.DataFrame] = []
    for index, quarter in enumerate(chosen_quarters):
        allocation = base + (1 if index < remainder else 0)
        group = work[work["_quarter"].eq(quarter)].sort_values(["commence_time", "event_id"], kind="stable")
        pieces.append(_evenly_spaced(group, min(allocation, len(group))))
    selected = pd.concat(pieces, ignore_index=True) if pieces else work.head(0).copy()
    if len(selected) < count:
        remaining = work[~work["event_id"].astype(str).isin(set(selected["event_id"].astype(str)))]
        selected = pd.concat([selected, _evenly_spaced(remaining, min(count - len(selected), len(remaining)))], ignore_index=True)
    return selected.drop(columns=["_quarter"], errors="ignore").sort_values(["commence_time", "event_id"], kind="stable")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a resumable, budget-capped V4.2 bookmaker coverage preflight.")
    parser.add_argument("--events-csv", required=True)
    parser.add_argument("--baseline", choices=PREFLIGHT_BASELINES, required=True)
    parser.add_argument("--target-stage", type=int, required=True)
    parser.add_argument("--max-probe-events", type=int, default=12)
    parser.add_argument("--snapshot-offset-hours", type=float, default=1.0)
    parser.add_argument("--max-preflight-credits", type=int, required=True)
    parser.add_argument("--max-campaign-credits", type=int, required=True)
    parser.add_argument("--discovery-credits", type=int, default=0)
    parser.add_argument("--max-cost-per-call", type=int, default=10)
    parser.add_argument("--bookmakers", nargs="+", default=list(DEFAULT_BOOKMAKERS))
    parser.add_argument("--output-dir", default="data/odds_api/preflight")
    parser.add_argument("--report-output", default="artifacts/coverage_preflight_v4_2.json")
    parser.add_argument("--candidate-output", default="artifacts/candidate_campaign_plan_v4_2.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument(
        "--retry-uncertain",
        action="store_true",
        help="Explicitly retry a probe whose provider billing outcome is uncertain.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.target_stage <= 0:
        raise ValueError("--target-stage must be positive")
    if args.max_probe_events <= 0:
        raise ValueError("--max-probe-events must be positive")
    if args.max_preflight_credits < 0 or args.discovery_credits < 0:
        raise ValueError("preflight credits must be non-negative")
    if args.discovery_credits > args.max_preflight_credits:
        raise ValueError("discovery already exceeded the preflight credit cap")
    if args.max_cost_per_call <= 0:
        raise ValueError("--max-cost-per-call must be positive")

    events_path = ROOT / args.events_csv
    events = pd.read_csv(events_path)
    required = {"event_id", "sport_key", "commence_time"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")
    events = events.copy()
    events["commence_time"] = pd.to_datetime(events["commence_time"], utc=True, errors="raise", format="mixed")
    events = events.sort_values(["commence_time", "event_id"], kind="stable").drop_duplicates("event_id")
    available_budget = int(args.max_preflight_credits) - int(args.discovery_credits)
    request_capacity = available_budget // int(args.max_cost_per_call)
    probe_count = min(len(events), int(args.max_probe_events), max(0, request_capacity))
    selected = _stratified_quarter_sample(events, probe_count) if probe_count else events.head(0).copy()
    selected["requested_snapshot_at"] = selected["commence_time"] - pd.to_timedelta(float(args.snapshot_offset_hours), unit="h")
    selected["snapshot_key"] = selected["requested_snapshot_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    requests = selected[["sport_key", "snapshot_key"]].drop_duplicates().reset_index(drop=True)
    requests["request_number"] = range(1, len(requests) + 1)

    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_material = {
        "schema_version": "1.0",
        "app_version": APP_VERSION,
        "baseline": args.baseline,
        "target_stage": int(args.target_stage),
        "max_probe_events": int(args.max_probe_events),
        "selected_probe_event_ids": selected["event_id"].astype(str).tolist(),
        "snapshot_offset_hours": float(args.snapshot_offset_hours),
        "max_preflight_credits": int(args.max_preflight_credits),
        "max_campaign_credits": int(args.max_campaign_credits),
        "discovery_credits": int(args.discovery_credits),
        "max_cost_per_call": int(args.max_cost_per_call),
        "bookmakers": list(args.bookmakers),
        "requests": requests.to_dict(orient="records"),
    }
    plan_id = "PFP-" + hashlib.sha256(_canonical_json(plan_material).encode("utf-8")).hexdigest()[:24].upper()
    plan = {**plan_material, "plan_id": plan_id, "request_count": len(requests), "execute": bool(args.execute)}
    _atomic_json(output_dir / "plan.json", plan)
    _atomic_csv(output_dir / "probe_events.csv", selected)
    _atomic_csv(output_dir / "requests.csv", requests)

    if not args.execute:
        print(json.dumps(plan, indent=2))
        print("ZERO-CREDIT PREFLIGHT PLAN: no provider request was executed.")
        return 0

    state_path = output_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "schema_version": "1.0",
        "plan_id": plan_id,
        "completed": [],
        "consumed_credits": int(args.discovery_credits),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if state.get("plan_id") != plan_id:
        raise RuntimeError("coverage preflight checkpoint belongs to a different immutable plan")
    completed = {int(value) for value in state.get("completed", [])}
    uncertain = {int(value) for value in state.get("uncertain", [])}
    consumed = int(state.get("consumed_credits") or 0)
    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    chunks = output_dir / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)

    for request in requests.to_dict(orient="records"):
        number = int(request["request_number"])
        if number in completed:
            continue
        if number in uncertain and not args.retry_uncertain:
            raise RuntimeError(
                f"probe request {number} has an uncertain billing outcome; verify provider usage and pass --retry-uncertain explicitly"
            )
        if consumed + int(args.max_cost_per_call) > int(args.max_preflight_credits):
            raise RuntimeError("preflight credit cap reached before next request")
        snapshot = str(request["snapshot_key"])
        try:
            response = client.historical_odds(
                str(request["sport_key"]),
                snapshot_at=snapshot,
                markets=("h2h",),
                bookmakers=args.bookmakers,
                force_refresh=bool(args.force_refresh),
            )
        except Exception:
            uncertain.add(number)
            state.update(
                {
                    "uncertain": sorted(uncertain),
                    "last_request": number,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _atomic_json(state_path, state)
            raise
        uncertain.discard(number)
        rows = normalize_odds_payload(response.payload)
        target_ids = set(
            selected.loc[selected["snapshot_key"].eq(snapshot), "event_id"].astype(str)
        )
        if not rows.empty:
            rows = rows[rows["event_id"].astype(str).isin(target_ids)].copy()
            rows["requested_snapshot_at"] = snapshot
        chunk_path = chunks / f"{number:06d}.csv"
        _atomic_csv(chunk_path, rows)
        actual_cost = 0 if response.from_cache else int(response.quota.last_cost or args.max_cost_per_call)
        if actual_cost < 0:
            raise RuntimeError("provider returned a negative quota cost")
        consumed += actual_cost
        if consumed > int(args.max_preflight_credits):
            raise RuntimeError("provider-reported cost exceeded preflight credit cap")
        completed.add(number)
        state.update(
            {
                "completed": sorted(completed),
                "uncertain": sorted(uncertain),
                "consumed_credits": consumed,
                "last_request": number,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _atomic_json(state_path, state)
        print(f"preflight {len(completed)}/{len(requests)} request={number} rows={len(rows)} consumed={consumed}")

    frames: list[pd.DataFrame] = []
    for path in sorted(chunks.glob("*.csv")):
        if not path.stat().st_size:
            continue
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        if not frame.empty:
            frames.append(frame)
    odds_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    _atomic_csv(output_dir / "historical_odds_long.csv", odds_rows)
    state.update({"status": "completed", "finished_at": datetime.now(timezone.utc).isoformat()})
    _atomic_json(state_path, state)

    report = build_coverage_preflight_report(
        selected,
        odds_rows,
        baseline=args.baseline,
        target_stage=args.target_stage,
        maximum_preflight_credits=args.max_preflight_credits,
        maximum_campaign_credits=args.max_campaign_credits,
        preflight_credits=consumed,
        estimated_snapshot_cost=float(args.max_cost_per_call),
        source_commit=(os.getenv("GITHUB_SHA") or os.getenv("SOURCE_COMMIT") or "unknown"),
        preflight_plan_id=plan_id,
        candidate_events=events,
    ).to_dict()
    report_path = ROOT / args.report_output
    _atomic_json(report_path, report)
    candidate_path = ROOT / args.candidate_output
    if report.get("candidate_campaign_plan"):
        _atomic_json(candidate_path, report["candidate_campaign_plan"])
    elif candidate_path.exists():
        candidate_path.unlink()
    matrix = pd.DataFrame(report["bookmaker_coverage"])
    _atomic_csv(ROOT / "artifacts/coverage_matrix_v4_2.csv", matrix)
    print(json.dumps(report, indent=2))
    return 0 if report["decision"] in {"VIABLE", "RISKY", "NOT_VIABLE"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
