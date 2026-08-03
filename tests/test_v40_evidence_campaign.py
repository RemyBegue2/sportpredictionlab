from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
from fastapi.testclient import TestClient

from sports_predictor.evidence_campaign import (
    build_campaign_plan,
    evaluate_scale_gate,
    next_stage,
)

ROOT = Path(__file__).resolve().parents[1]


def _good_evidence(completed: int = 30) -> dict:
    return {
        "consumed_credits": completed * 10,
        "funnel": {"completed_event_snapshots": completed, "benchmark_ready_events": completed, "consensus_ready_events": completed, "reliably_matched_events": completed, "accepted_events": completed},
        "rates": {
            "provider_return_coverage": 0.95,
            "reliable_matching": 0.97,
            "consensus_coverage": 0.90,
        },
        "counts": {"quarantined_temporal_rows": 0, "duplicate_rows": 0, "matching_collisions": 0},
        "gates": {"technical_integrity": {"accepted": True}},
        "quality_gate": {"status": "PASS", "accepted": True},
    }


def _viable_preflight(stage: int, max_credits: int, *, baseline: str = "consensus", recommended: int | None = None) -> dict:
    recommended = int(recommended or stage)
    ids = sorted(f"event-{index}" for index in range(max(recommended, stage)))
    candidate = {
        "schema_version": "1.0",
        "app_version": "4.3.0",
        "baseline": baseline,
        "campaign_type": "french_market_comparison",
        "target_stage": stage,
        "recommended_selected_events": recommended,
        "start_date": "2023-01-01",
        "end_date": "2026-07-31",
        "maximum_campaign_credits": max_credits,
        "estimated_snapshot_cost": 10.0,
        "candidate_event_pool_count": len(ids),
        "candidate_event_ids_sha256": hashlib.sha256(json.dumps(ids, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(),
        "candidate_event_ids": ids,
        "selection_policy": "chronological_evenly_spaced_without_results",
    }
    candidate_id = "CPL-" + hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:24].upper()
    return {
        "preflight_id": f"PFL-TEST-{baseline}-{stage}-{max_credits}",
        "decision": "VIABLE",
        "accepted": True,
        "baseline": baseline,
        "campaign_type": "french_market_comparison",
        "target_stage": stage,
        "maximum_campaign_credits": max_credits,
        "estimated_snapshot_cost": 10.0,
        "candidate_campaign_plan": {**candidate, "candidate_plan_id": candidate_id},
    }


def test_v40_dry_run_is_zero_credit_and_never_executes() -> None:
    plan = build_campaign_plan(
        mode="dry_run",
        target_stage=30,
        max_credits=350,
        baseline="consensus",
        start_date="2023-01-01",
        end_date="2026-07-31",
    )
    assert plan.execution_allowed is False
    assert plan.execution_reason == "dry_run_never_calls_provider"
    assert plan.consumes_provider_credits is False
    assert plan.campaign_id.startswith("CMP-")


def test_v40_first_stage_requires_budget_for_complete_stage() -> None:
    blocked = build_campaign_plan(
        mode="start_next_stage",
        target_stage=30,
        max_credits=120,
        baseline="consensus",
        start_date="2023-01-01",
        end_date="2026-07-31",
        coverage_preflight=_viable_preflight(30, 120),
    )
    allowed = build_campaign_plan(
        mode="start_next_stage",
        target_stage=30,
        max_credits=350,
        baseline="consensus",
        start_date="2023-01-01",
        end_date="2026-07-31",
        coverage_preflight=_viable_preflight(30, 350),
    )
    assert blocked.execution_allowed is False
    assert blocked.execution_reason == "budget_cannot_fund_preflight_recommended_sample"
    assert allowed.execution_allowed is True
    assert allowed.estimated_events_this_run == 30


def test_v40_next_stage_requires_previous_quality_gate() -> None:
    good = build_campaign_plan(
        mode="start_next_stage",
        target_stage=100,
        max_credits=1200,
        baseline="consensus",
        previous_evidence=_good_evidence(30),
        start_date="2023-01-01",
        end_date="2026-07-31",
        coverage_preflight=_viable_preflight(100, 1200),
    )
    bad_evidence = _good_evidence(30)
    bad_evidence["rates"]["reliable_matching"] = 0.80
    bad = build_campaign_plan(
        mode="start_next_stage",
        target_stage=100,
        max_credits=1200,
        baseline="consensus",
        previous_evidence=bad_evidence,
        start_date="2023-01-01",
        end_date="2026-07-31",
        coverage_preflight=_viable_preflight(100, 1200),
    )
    assert good.execution_allowed is True
    assert bad.execution_allowed is False
    assert bad.execution_reason == "previous_stage_quality_gate_failed"
    assert evaluate_scale_gate(bad_evidence)["accepted"] is False
    assert next_stage(30) == 100


def test_v40_campaign_planner_cli_is_file_only(tmp_path: Path) -> None:
    output = tmp_path / "campaign.json"
    env = dict(**__import__("os").environ)
    env["DATABASE_URL"] = "postgresql://user:password@example.com:/railway"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.plan_evidence_campaign",
            "--mode",
            "dry_run",
            "--target-stage",
            "30",
            "--max-credits",
            "350",
            "--baseline",
            "consensus",
            "--start-date",
            "2023-01-01",
            "--end-date",
            "2026-07-31",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["app_version"] == "4.3.0"
    assert "ZERO-CREDIT CAMPAIGN PLAN" in result.stdout


def test_v40_select_campaign_events_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    output = tmp_path / "selected.csv"
    frame = pd.DataFrame(
        {
            "sport_key": ["soccer_epl"] * 10,
            "event_id": [f"event-{index}" for index in range(10)],
            "commence_time": pd.date_range("2025-01-01", periods=10, freq="7D", tz="UTC"),
        }
    )
    frame.to_csv(source, index=False)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.select_campaign_events",
            "--input",
            str(source),
            "--target",
            "4",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    selected = pd.read_csv(output)
    assert selected["event_id"].tolist() == ["event-0", "event-3", "event-6", "event-9"]


def test_v40_api_frontend_and_workflow_contract() -> None:
    import webapp

    with TestClient(webapp.app) as client:
        release = client.get("/api/release")
        campaign = client.get("/api/evidence-campaign")
    assert release.status_code == 200
    assert release.json()["version"] == "4.3.0"
    assert campaign.status_code == 200
    assert campaign.json()["report"]["automatic_model_promotion"] is False

    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "run-evidence-campaign.yml").read_text(encoding="utf-8")
    for element_id in ("campaignDecision", "campaignCompleted", "campaignNext", "campaignBudget"):
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js
    assert "app.js?v=4.3.0" in html
    assert "plan_request_id" not in workflow
    assert "Test before any provider request" in workflow
    assert workflow.index("Test before any provider request") < workflow.index("Discover historical events")
    assert "DATABASE_URL" not in workflow
    assert "EXECUTE_CAMPAIGN" in workflow
    assert "restore_campaign_state" in workflow
    assert "evidence-campaign-state-" in workflow
    assert "automatic_model_promotion" not in workflow


def test_v40_stage_100_provider_plan_is_immutable_and_dry_runnable(tmp_path: Path) -> None:
    events = pd.DataFrame(
        {
            "sport_key": ["soccer_epl"] * 100,
            "event_id": [f"provider-{index}" for index in range(100)],
            "commence_time": pd.date_range("2023-01-01", periods=100, freq="7D", tz="UTC"),
            "home_team": [f"Home {index}" for index in range(100)],
            "away_team": [f"Away {index}" for index in range(100)],
        }
    )
    events_csv = tmp_path / "events.csv"
    plan_dir = tmp_path / "plan"
    events.to_csv(events_csv, index=False)
    plan_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.plan_historical_backfill",
            "--events-csv",
            str(events_csv),
            "--horizons",
            "1",
            "--no-closing",
            "--bookmakers",
            "winamax_fr",
            "betclic_fr",
            "unibet_fr",
            "pmu_fr",
            "pinnacle",
            "--max-credits",
            "1100",
            "--full",
            "--output-dir",
            str(plan_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert plan_result.returncode == 0, plan_result.stderr + plan_result.stdout
    plan = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
    assert plan["event_count"] == 100
    assert plan["execution_mode"] == "full"
    dry_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_historical_backfill",
            "--plan-dir",
            str(plan_dir),
            "--max-credits",
            "1100",
            "--storage",
            "files",
            "--approve-plan",
            plan["plan_id"],
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert dry_run.returncode == 0, dry_run.stderr + dry_run.stdout
    assert "DRY-RUN only" in dry_run.stdout


def test_v40_continue_reuses_committed_campaign_dates(tmp_path: Path) -> None:
    output = tmp_path / "campaign.json"
    output.write_text(
        json.dumps(
            {
                "target_stage": 30,
                "baseline": "consensus",
                "max_credits": 350,
                "start_date": "2023-01-01",
                "end_date": "2025-12-31",
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.plan_evidence_campaign",
            "--mode",
            "continue_current_stage",
            "--target-stage",
            "30",
            "--max-credits",
            "350",
            "--baseline",
            "consensus",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["end_date"] == "2025-12-31"


def test_v40_checkpoint_restore_requires_matching_plan(tmp_path: Path) -> None:
    current_plan = tmp_path / "current.json"
    artifact_root = tmp_path / "artifact"
    destination = tmp_path / "destination"
    plan = {
        "target_stage": 30,
        "baseline": "consensus",
        "max_credits": 350,
        "start_date": "2023-01-01",
        "end_date": "2025-12-31",
    }
    current_plan.write_text(json.dumps(plan), encoding="utf-8")
    (artifact_root / "artifacts").mkdir(parents=True)
    (artifact_root / "artifacts" / "evidence_campaign_plan_v4.json").write_text(json.dumps(plan), encoding="utf-8")
    backfill = artifact_root / "data" / "odds_api" / "campaign" / "backfill"
    backfill.mkdir(parents=True)
    (backfill / "plan.json").write_text(json.dumps({"plan_id": "p1"}), encoding="utf-8")
    (backfill / "state.json").write_text(json.dumps({"completed": [1, 2], "consumed_credits": 20}), encoding="utf-8")
    campaign_dir = artifact_root / "data" / "odds_api" / "campaign"
    (campaign_dir / "event_discovery_state.json").write_text(json.dumps({"consumed_credits": 14}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.restore_campaign_state",
            "--current-plan",
            str(current_plan),
            "--artifact-root",
            str(artifact_root),
            "--destination-root",
            str(destination),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    restored = destination / "data" / "odds_api" / "campaign" / "backfill" / "state.json"
    assert restored.exists()
    assert json.loads(restored.read_text(encoding="utf-8"))["completed"] == [1, 2]
