from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

from sports_predictor.coverage_preflight import (
    baseline_ready_event_ids,
    build_coverage_preflight_report,
    validate_preflight_for_campaign,
    wilson_interval,
)
from sports_predictor.evidence_campaign import build_campaign_plan

ROOT = Path(__file__).resolve().parents[1]


def _events(count: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sport_key": ["soccer_epl"] * count,
            "event_id": [f"event-{index}" for index in range(count)],
            "commence_time": pd.date_range("2025-01-01", periods=count, freq="7D", tz="UTC"),
            "home_team": [f"Home {index}" for index in range(count)],
            "away_team": [f"Away {index}" for index in range(count)],
        }
    )


def _odds(events: pd.DataFrame, ready_count: int, *, winamax: bool = True, pinnacle_only: bool = False) -> pd.DataFrame:
    rows: list[dict] = []
    for index, event in enumerate(events.to_dict(orient="records")):
        if index >= ready_count:
            continue
        bookmakers = ["pinnacle"] if pinnacle_only else ["betclic_fr", "pinnacle"]
        if winamax:
            bookmakers.append("winamax_fr")
        for bookmaker in bookmakers:
            for outcome, price in ((event["home_team"], 2.2), ("Draw", 3.4), (event["away_team"], 3.5)):
                rows.append(
                    {
                        "event_id": event["event_id"],
                        "commence_time": event["commence_time"],
                        "bookmaker_key": bookmaker,
                        "market_key": "h2h",
                        "outcome_name": outcome,
                        "price": price,
                        "requested_snapshot_at": pd.Timestamp(event["commence_time"]) - pd.Timedelta(hours=1),
                    }
                )
    return pd.DataFrame(rows)


def _viable_report(*, stage: int = 30, budget: int = 650, recommended: int = 32) -> dict:
    candidate_ids = sorted(f"event-{index}" for index in range(max(recommended, 40)))
    candidate = {
        "schema_version": "1.0",
        "app_version": "4.2.0",
        "baseline": "consensus",
        "campaign_type": "french_market_comparison",
        "target_stage": stage,
        "recommended_selected_events": recommended,
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "maximum_campaign_credits": budget,
        "estimated_snapshot_cost": 10.0,
        "candidate_event_pool_count": len(candidate_ids),
        "candidate_event_ids_sha256": hashlib.sha256(json.dumps(candidate_ids, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(),
        "candidate_event_ids": candidate_ids,
        "selection_policy": "chronological_evenly_spaced_without_results",
    }
    candidate_id = "CPL-" + hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:24].upper()
    return {
        "preflight_id": "PFL-TEST-VIABLE",
        "decision": "VIABLE",
        "accepted": True,
        "baseline": "consensus",
        "campaign_type": "french_market_comparison",
        "target_stage": stage,
        "maximum_campaign_credits": budget,
        "estimated_snapshot_cost": 10.0,
        "candidate_campaign_plan": {**candidate, "candidate_plan_id": candidate_id},
    }


def test_wilson_interval_is_conservative_for_small_samples() -> None:
    low, high = wilson_interval(1, 5)
    assert 0.03 < low < 0.05
    assert 0.60 < high < 0.65
    low_all, _ = wilson_interval(10, 10)
    assert low_all > 0.70


def test_consensus_requires_two_independent_complete_bookmakers() -> None:
    events = _events(1)
    one_book = _odds(events, 1, winamax=False, pinnacle_only=True)
    assert baseline_ready_event_ids(one_book, baseline="consensus") == set()
    two_books = _odds(events, 1, winamax=False)
    assert baseline_ready_event_ids(two_books, baseline="consensus") == {"event-0"}


def test_previous_realistic_coverage_is_rejected_before_full_backfill() -> None:
    events = _events(10)
    report = build_coverage_preflight_report(
        events,
        _odds(events, 2),
        baseline="consensus",
        target_stage=30,
        maximum_preflight_credits=70,
        maximum_campaign_credits=650,
        preflight_credits=64,
        candidate_events=_events(100),
    ).to_dict()
    assert report["decision"] == "NOT_VIABLE"
    assert report["reason"] == "baseline_coverage_upper_bound_below_threshold"
    assert report["candidate_campaign_plan"] is None


def test_full_probe_coverage_creates_oversampled_viable_candidate() -> None:
    events = _events(10)
    report = build_coverage_preflight_report(
        events,
        _odds(events, 10),
        baseline="consensus",
        target_stage=30,
        maximum_preflight_credits=120,
        maximum_campaign_credits=650,
        preflight_credits=100,
        candidate_events=_events(100),
    ).to_dict()
    assert report["decision"] == "VIABLE"
    assert report["recommended_selected_events"] == 32
    assert report["candidate_campaign_plan"]["recommended_selected_events"] == 32
    assert report["campaign_snapshot_capacity"] == 63
    assert report["sampling_method"] == "deterministic_quarter_stratified_without_outcomes"
    assert report["uncertainty_method"] == "wilson_score_diagnostic"
    assert "not a formal random-sample" in report["uncertainty_limitations"]


def test_observed_threshold_without_statistical_support_is_risky() -> None:
    events = _events(10)
    report = build_coverage_preflight_report(
        events,
        _odds(events, 7),
        baseline="consensus",
        target_stage=30,
        maximum_preflight_credits=120,
        maximum_campaign_credits=650,
        preflight_credits=100,
        candidate_events=_events(100),
    ).to_dict()
    assert report["decision"] == "RISKY"
    assert report["accepted"] is False


def test_budget_can_make_good_coverage_not_viable() -> None:
    events = _events(10)
    report = build_coverage_preflight_report(
        events,
        _odds(events, 10),
        baseline="consensus",
        target_stage=30,
        maximum_preflight_credits=120,
        maximum_campaign_credits=300,
        preflight_credits=100,
        candidate_events=_events(100),
    ).to_dict()
    assert report["decision"] == "NOT_VIABLE"
    assert report["reason"] == "campaign_budget_cannot_fund_projected_ready_events"


def test_pinnacle_is_a_separate_experiment_type() -> None:
    events = _events(10)
    report = build_coverage_preflight_report(
        events,
        _odds(events, 10, winamax=False, pinnacle_only=True),
        baseline="pinnacle",
        target_stage=30,
        maximum_preflight_credits=120,
        maximum_campaign_credits=650,
        preflight_credits=100,
        candidate_events=_events(100),
    ).to_dict()
    assert report["campaign_type"] == "provider_available_benchmark"
    assert report["candidate_campaign_plan"]["campaign_type"] == "provider_available_benchmark"


def test_campaign_requires_exact_viable_preflight() -> None:
    missing = build_campaign_plan(
        mode="start_next_stage",
        target_stage=30,
        max_credits=650,
        baseline="consensus",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )
    assert missing.execution_allowed is False
    assert missing.execution_reason == "coverage_preflight_missing"

    report = _viable_report()
    valid, reason = validate_preflight_for_campaign(
        report,
        baseline="consensus",
        target_stage=30,
        maximum_campaign_credits=650,
    )
    assert valid is True
    assert reason == "coverage_preflight_viable"

    allowed = build_campaign_plan(
        mode="start_next_stage",
        target_stage=30,
        max_credits=650,
        baseline="consensus",
        coverage_preflight=report,
    )
    assert allowed.execution_allowed is True
    assert allowed.recommended_selected_events == 32
    assert allowed.start_date == "2025-01-01"
    assert allowed.end_date == "2025-12-31"
    assert allowed.coverage_preflight_id == "PFL-TEST-VIABLE"


def test_preflight_mismatch_is_rejected() -> None:
    report = _viable_report()
    valid, reason = validate_preflight_for_campaign(
        report,
        baseline="winamax",
        target_stage=30,
        maximum_campaign_credits=650,
    )
    assert valid is False
    assert reason == "coverage_preflight_baseline_mismatch"


def test_preflight_runner_is_resumable_and_budget_capped(tmp_path: Path, monkeypatch) -> None:
    import scripts.run_coverage_preflight as runner

    events = _events(2)
    events.to_csv(tmp_path / "events.csv", index=False)

    @dataclass
    class Quota:
        last_cost: int = 10
        remaining: int = 999

    @dataclass
    class Response:
        payload: list[dict]
        quota: Quota
        from_cache: bool = False

    class FakeClient:
        calls = 0

        def __init__(self, config):
            pass

        def historical_odds(self, sport_key: str, *, snapshot_at: str, markets, bookmakers, force_refresh: bool):
            type(self).calls += 1
            target = events.iloc[type(self).calls - 1]
            payload = [
                {
                    "id": target["event_id"],
                    "sport_key": sport_key,
                    "commence_time": pd.Timestamp(target["commence_time"]).isoformat().replace("+00:00", "Z"),
                    "home_team": target["home_team"],
                    "away_team": target["away_team"],
                    "bookmakers": [
                        {
                            "key": key,
                            "title": key,
                            "last_update": snapshot_at,
                            "markets": [
                                {
                                    "key": "h2h",
                                    "last_update": snapshot_at,
                                    "outcomes": [
                                        {"name": target["home_team"], "price": 2.2},
                                        {"name": "Draw", "price": 3.4},
                                        {"name": target["away_team"], "price": 3.5},
                                    ],
                                }
                            ],
                        }
                        for key in ("betclic_fr", "pinnacle", "winamax_fr")
                    ],
                }
            ]
            return Response(payload=payload, quota=Quota())

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "OddsApiClient", FakeClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_coverage_preflight",
            "--events-csv",
            "events.csv",
            "--baseline",
            "consensus",
            "--target-stage",
            "1",
            "--max-probe-events",
            "2",
            "--max-preflight-credits",
            "20",
            "--max-campaign-credits",
            "100",
            "--output-dir",
            "preflight",
            "--report-output",
            "report.json",
            "--candidate-output",
            "candidate.json",
            "--execute",
        ],
    )
    assert runner.main() == 0
    state = json.loads((tmp_path / "preflight" / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["completed"] == [1, 2]
    assert state["consumed_credits"] == 20
    assert FakeClient.calls == 2

    assert runner.main() == 0
    assert FakeClient.calls == 2


def test_workflow_requires_preflight_before_campaign() -> None:
    workflow = (ROOT / ".github" / "workflows" / "estimate-evidence-coverage.yml").read_text(encoding="utf-8")
    campaign = (ROOT / ".github" / "workflows" / "run-evidence-campaign.yml").read_text(encoding="utf-8")
    assert "EXECUTE_PREFLIGHT" in workflow
    assert "run_coverage_preflight" in workflow
    assert "coverage_preflight_v4_2.json" in workflow
    assert "coverage_preflight_v4_2.json" in campaign
    assert "recommended_events" in campaign
    assert "railway up --ci" not in campaign
    assert "INPUT_CONFIRMATION" in workflow
    assert "${{ inputs.confirmation }}'" not in workflow


def test_preflight_api_and_frontend_surface() -> None:
    import webapp
    from fastapi.testclient import TestClient

    response = TestClient(webapp.app).get("/api/coverage-preflight")
    assert response.status_code == 200
    assert "report" in response.json()
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    for element_id in (
        "preflightDecision",
        "preflightCoverage",
        "preflightRecommended",
        "preflightCredits",
    ):
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js
    assert "/api/coverage-preflight" in js


def test_uncertain_preflight_probe_requires_explicit_retry(tmp_path: Path, monkeypatch) -> None:
    import scripts.run_coverage_preflight as runner

    events = _events(1)
    events.to_csv(tmp_path / "events.csv", index=False)

    class FailingClient:
        def __init__(self, config):
            pass

        def historical_odds(self, *args, **kwargs):
            raise RuntimeError("simulated transport interruption")

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "OddsApiClient", FailingClient)
    base_argv = [
        "run_coverage_preflight",
        "--events-csv",
        "events.csv",
        "--baseline",
        "consensus",
        "--target-stage",
        "1",
        "--max-probe-events",
        "1",
        "--max-preflight-credits",
        "10",
        "--max-campaign-credits",
        "100",
        "--output-dir",
        "preflight",
        "--report-output",
        "report.json",
        "--candidate-output",
        "candidate.json",
        "--execute",
    ]
    monkeypatch.setattr(sys, "argv", base_argv)
    try:
        runner.main()
    except RuntimeError as exc:
        assert "simulated transport interruption" in str(exc)
    else:
        raise AssertionError("provider interruption was not propagated")
    state = json.loads((tmp_path / "preflight" / "state.json").read_text(encoding="utf-8"))
    assert state["uncertain"] == [1]

    class ShouldNotRunClient:
        def __init__(self, config):
            pass

        def historical_odds(self, *args, **kwargs):
            raise AssertionError("uncertain request was replayed without approval")

    monkeypatch.setattr(runner, "OddsApiClient", ShouldNotRunClient)
    monkeypatch.setattr(sys, "argv", base_argv)
    try:
        runner.main()
    except RuntimeError as exc:
        assert "uncertain billing outcome" in str(exc)
    else:
        raise AssertionError("uncertain probe should require --retry-uncertain")


def test_empty_provider_payload_completes_with_not_viable_report(tmp_path: Path, monkeypatch) -> None:
    import scripts.run_coverage_preflight as runner

    events = _events(1)
    events.to_csv(tmp_path / "events.csv", index=False)

    @dataclass
    class Quota:
        last_cost: int = 10
        remaining: int = 999

    @dataclass
    class Response:
        payload: list[dict]
        quota: Quota
        from_cache: bool = False

    class EmptyClient:
        def __init__(self, config):
            pass

        def historical_odds(self, *args, **kwargs):
            return Response(payload=[], quota=Quota())

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "OddsApiClient", EmptyClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_coverage_preflight",
            "--events-csv",
            "events.csv",
            "--baseline",
            "consensus",
            "--target-stage",
            "1",
            "--max-probe-events",
            "1",
            "--max-preflight-credits",
            "10",
            "--max-campaign-credits",
            "100",
            "--output-dir",
            "preflight",
            "--report-output",
            "report.json",
            "--candidate-output",
            "candidate.json",
            "--execute",
        ],
    )
    assert runner.main() == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["decision"] == "NOT_VIABLE"
    assert report["baseline_ready_events"] == 0
    assert not (tmp_path / "candidate.json").exists()


def test_campaign_planner_materializes_exact_embedded_candidate(tmp_path: Path, monkeypatch) -> None:
    import scripts.plan_evidence_campaign as planner

    report = _viable_report()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "coverage_preflight_v4_2.json").write_text(json.dumps(report), encoding="utf-8")
    (artifacts / "candidate_campaign_plan_v4_2.json").write_text('{"stale": true}', encoding="utf-8")

    monkeypatch.setattr(planner, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_evidence_campaign",
            "--mode",
            "start_next_stage",
            "--target-stage",
            "30",
            "--max-credits",
            "650",
            "--baseline",
            "consensus",
        ],
    )
    assert planner.main() == 0
    materialized = json.loads((artifacts / "candidate_campaign_plan_v4_2.json").read_text(encoding="utf-8"))
    assert materialized == report["candidate_campaign_plan"]


def test_selector_rejects_tampered_candidate_plan(tmp_path: Path, monkeypatch) -> None:
    import scripts.select_campaign_events as selector

    events = _events(40)
    events.to_csv(tmp_path / "events.csv", index=False)
    candidate = _viable_report(recommended=32)["candidate_campaign_plan"]
    candidate["start_date"] = "2024-01-01"
    (tmp_path / "candidate.json").write_text(json.dumps(candidate), encoding="utf-8")

    monkeypatch.setattr(selector, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "select_campaign_events",
            "--input",
            "events.csv",
            "--target",
            "32",
            "--candidate-plan",
            "candidate.json",
            "--output",
            "selected.csv",
        ],
    )
    try:
        selector.main()
    except ValueError as exc:
        assert "immutable plan integrity" in str(exc)
    else:
        raise AssertionError("tampered candidate plan was accepted")


def test_continue_revalidates_exact_candidate_plan() -> None:
    report = _viable_report()
    initial = build_campaign_plan(
        mode="start_next_stage",
        target_stage=30,
        max_credits=650,
        baseline="consensus",
        coverage_preflight=report,
    )
    assert initial.execution_allowed is True
    current = initial.to_dict()

    tampered = json.loads(json.dumps(report))
    tampered["candidate_campaign_plan"]["start_date"] = "2024-01-01"
    resumed = build_campaign_plan(
        mode="continue_current_stage",
        target_stage=30,
        max_credits=650,
        baseline="consensus",
        current_campaign=current,
        start_date=initial.start_date,
        end_date=initial.end_date,
        coverage_preflight=tampered,
    )
    assert resumed.execution_allowed is False
    assert resumed.execution_reason in {
        "continue_candidate_plan_must_match_existing_campaign",
        "coverage_preflight_candidate_plan_integrity_failed",
    }
