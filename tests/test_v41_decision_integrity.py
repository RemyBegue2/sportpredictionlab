from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

import pandas as pd

from sports_predictor.evidence_campaign import build_campaign_plan, evaluate_scale_gate, next_stage
from sports_predictor.evidence_quality import build_evidence_quality_report
from sports_predictor.event_matching import match_events_to_results
from sports_predictor.odds_data import bookmaker_h2h_markets, consensus_h2h


def _stage_evidence(*, consensus: float = 0.9, winamax: float = 0.9) -> dict:
    return {
        "funnel": {
            "benchmark_ready_events": 30,
            "accepted_events": 30,
            "reliably_matched_events": 30,
            "consensus_ready_events": 30,
            "winamax_ready_events": 30,
        },
        "rates": {
            "provider_return_coverage": 0.90,
            "reliable_matching": 0.97,
            "consensus_coverage": consensus,
            "winamax_coverage": winamax,
        },
        "counts": {
            "quarantined_temporal_rows": 0,
            "duplicate_rows": 0,
            "matching_collisions": 0,
        },
        "gates": {"technical_integrity": {"accepted": True}},
    }


def test_continue_mode_cannot_invent_a_higher_stage() -> None:
    evidence = _stage_evidence()
    blocked = build_campaign_plan(
        mode="continue_current_stage",
        target_stage=100,
        max_credits=1200,
        baseline="consensus",
        previous_evidence=evidence,
        current_campaign={
            "app_version": "4.1.3",
            "target_stage": 30,
            "baseline": "consensus",
            "max_credits": 1200,
            "start_date": "2023-01-01",
            "end_date": "2026-07-31",
        },
        start_date="2023-01-01",
        end_date="2026-07-31",
    )
    assert blocked.execution_allowed is False
    assert blocked.execution_reason == "continue_parameters_must_match_existing_campaign"


def test_continue_mode_allows_only_the_exact_existing_incomplete_stage() -> None:
    evidence = _stage_evidence()
    current = {
        "app_version": "4.1.3",
        "target_stage": 100,
        "baseline": "consensus",
        "max_credits": 1200,
        "start_date": "2023-01-01",
        "end_date": "2026-07-31",
    }
    allowed = build_campaign_plan(
        mode="continue_current_stage",
        target_stage=100,
        max_credits=1200,
        baseline="consensus",
        previous_evidence=evidence,
        current_campaign=current,
        start_date="2023-01-01",
        end_date="2026-07-31",
    )
    assert allowed.execution_allowed is True


def test_scale_gate_is_baseline_specific_and_terminal_stage_has_no_successor() -> None:
    evidence = _stage_evidence(consensus=0.9, winamax=0.0)
    assert evaluate_scale_gate(evidence, baseline="consensus")["status"] == "PASS"
    assert evaluate_scale_gate(evidence, baseline="winamax")["status"] == "HOLD"
    assert next_stage(1000) is None


def test_matching_is_bijective_and_quarantines_collision() -> None:
    results = pd.DataFrame(
        [
            {
                "date": "2025-01-01T15:00:00Z",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "home_goals": 2,
                "away_goals": 1,
            }
        ]
    )
    events = pd.DataFrame(
        [
            {
                "event_id": "provider-a",
                "commence_time": "2025-01-01T15:00:00Z",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
            },
            {
                "event_id": "provider-b",
                "commence_time": "2025-01-01T15:01:00Z",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
            },
        ]
    )
    mapping = match_events_to_results(events, results)
    assert mapping["status"].value_counts().to_dict() == {"matched": 1, "collision": 1}
    assert mapping.loc[mapping["status"].eq("matched"), "result_index"].is_unique


def test_consensus_requires_two_independent_books_after_winamax_exclusion() -> None:
    rows = []
    for bookmaker in ("winamax_fr", "betclic_fr"):
        for outcome, price in (("Arsenal", 2.0), ("Draw", 3.5), ("Chelsea", 4.0)):
            rows.append(
                {
                    "event_id": "event-1",
                    "sport_key": "soccer_epl",
                    "commence_time": "2025-01-01T15:00:00Z",
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "bookmaker_key": bookmaker,
                    "bookmaker_title": bookmaker,
                    "market_key": "h2h",
                    "outcome_name": outcome,
                    "price": price,
                    "market_last_update": "2025-01-01T13:59:00Z",
                    "snapshot_time": "2025-01-01T14:00:00Z",
                    "requested_snapshot_at": "2025-01-01T14:00:00Z",
                }
            )
    markets = bookmaker_h2h_markets(pd.DataFrame(rows))
    assert consensus_h2h(markets, exclude=("winamax_fr",)) is None


def test_canonical_report_passes_only_benchmark_ready_unique_events() -> None:
    events = []
    odds = []
    matches = []
    targets = []
    requests = []
    start = pd.Timestamp("2025-01-01T15:00:00Z")
    for index in range(30):
        commence = start + pd.Timedelta(days=index)
        snapshot = commence - pd.Timedelta(hours=1)
        event_id = f"event-{index:02d}"
        home = f"Home {index}"
        away = f"Away {index}"
        events.append({"sport_key": "soccer_epl", "event_id": event_id, "commence_time": commence, "home_team": home, "away_team": away})
        targets.append({"sport_key": "soccer_epl", "event_id": event_id, "commence_time": commence, "snapshot_at": snapshot, "stage": "t-1h"})
        requests.append({"sport_key": "soccer_epl", "snapshot_at": snapshot, "request_number": index + 1})
        matches.append({"provider_event_id": event_id, "result_index": index, "status": "matched", "confidence": 1.0})
        for bookmaker in ("winamax_fr", "betclic_fr", "pinnacle"):
            for outcome, price in ((home, 2.1), ("Draw", 3.4), (away, 3.2)):
                odds.append(
                    {
                        "sport_key": "soccer_epl",
                        "event_id": event_id,
                        "commence_time": commence,
                        "home_team": home,
                        "away_team": away,
                        "bookmaker_key": bookmaker,
                        "bookmaker_title": bookmaker,
                        "market_key": "h2h",
                        "outcome_name": outcome,
                        "price": price,
                        "requested_snapshot_at": snapshot,
                    }
                )
    # A valid-looking row outside the immutable target plan must not inflate coverage or stage counts.
    stray_commence = start + pd.Timedelta(days=60)
    stray_snapshot = stray_commence - pd.Timedelta(hours=1)
    for bookmaker in ("winamax_fr", "betclic_fr", "pinnacle"):
        for outcome, price in (("Stray Home", 2.1), ("Draw", 3.4), ("Stray Away", 3.2)):
            odds.append(
                {
                    "sport_key": "soccer_epl",
                    "event_id": "stray-event",
                    "commence_time": stray_commence,
                    "home_team": "Stray Home",
                    "away_team": "Stray Away",
                    "bookmaker_key": bookmaker,
                    "bookmaker_title": bookmaker,
                    "market_key": "h2h",
                    "outcome_name": outcome,
                    "price": price,
                    "requested_snapshot_at": stray_snapshot,
                }
            )

    report = build_evidence_quality_report(
        plan={"bookmakers": ["winamax_fr", "betclic_fr", "pinnacle"], "max_credits": 350},
        state={"status": "completed", "completed": list(range(1, 31)), "consumed_credits": 300},
        odds_rows=pd.DataFrame(odds),
        events=pd.DataFrame(events),
        matches=pd.DataFrame(matches),
        requests=pd.DataFrame(requests),
        targets=pd.DataFrame(targets),
        discovery_state={"status": "completed", "consumed_credits": 14, "event_count": 30},
        campaign_plan={"campaign_id": "CMP-X", "campaign_key": "CPK-X", "baseline": "consensus", "target_stage": 30, "max_credits": 350},
    )
    assert report["decision_gate"]["status"] == "PASS"
    assert report["funnel"]["benchmark_ready_events"] == 30
    assert report["funnel"]["accepted_events"] == 30
    assert report["rates"]["provider_return_coverage"] == 1.0
    assert report["credits"] == {
        "discovery_credits": 14,
        "snapshot_credits": 300,
        "total_credits": 314,
        "maximum_credits": 350,
        "remaining_credits": 36,
    }


def test_discovery_checkpoint_survives_mid_run_failure(tmp_path: Path, monkeypatch) -> None:
    import scripts.discover_historical_events as discovery

    @dataclass
    class Quota:
        remaining: int = 999
        last_cost: int | None = 1

    @dataclass
    class Response:
        payload: dict
        quota: Quota
        from_cache: bool = False
        request_fingerprint: str = "fingerprint"

    class FailingClient:
        calls = 0

        def __init__(self, config):
            pass

        def historical_events(self, sport_key: str, *, snapshot_at: str, force_refresh: bool):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated interruption")
            return Response(
                payload={
                    "timestamp": snapshot_at,
                    "data": [
                        {
                            "id": "event-a",
                            "sport_key": sport_key,
                            "commence_time": "2025-01-02T15:00:00Z",
                            "home_team": "Arsenal",
                            "away_team": "Chelsea",
                        }
                    ],
                },
                quota=Quota(),
            )

    monkeypatch.setattr(discovery, "ROOT", tmp_path)
    monkeypatch.setattr(discovery, "OddsApiClient", FailingClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "discover_historical_events",
            "--sport-key",
            "soccer_epl",
            "--start",
            "2025-01-01",
            "--end",
            "2025-01-02",
            "--max-calls",
            "2",
            "--max-credits",
            "5",
            "--output",
            "campaign/events.csv",
            "--execute",
        ],
    )
    try:
        discovery.main()
    except RuntimeError as exc:
        assert "simulated interruption" in str(exc)
    else:
        raise AssertionError("failure was not propagated")

    state = json.loads((tmp_path / "campaign" / "event_discovery_state.json").read_text(encoding="utf-8"))
    assert state["completed_call_numbers"] == [1]
    assert state["consumed_credits"] == 1
    assert state["uncertain_calls"] == [2]
    saved = pd.read_csv(tmp_path / "campaign" / "events.csv")
    assert saved["event_id"].tolist() == ["event-a"]


def test_incomplete_evidence_is_hold_but_temporal_corruption_is_fail() -> None:
    empty = build_evidence_quality_report(
        plan={"bookmakers": ["winamax_fr", "betclic_fr", "pinnacle"], "max_credits": 20},
        state={"status": "in_progress", "completed": [], "consumed_credits": 0},
        odds_rows=pd.DataFrame(),
        events=pd.DataFrame(),
        matches=pd.DataFrame(),
        requests=pd.DataFrame(),
        targets=pd.DataFrame(),
        campaign_plan={"baseline": "consensus", "target_stage": 30, "max_credits": 20},
    )
    assert empty["gates"]["technical_integrity"]["status"] == "HOLD"
    assert empty["decision_gate"]["status"] == "HOLD"

    corrupt = pd.DataFrame(
        [
            {
                "event_id": "event-1",
                "commence_time": "2025-01-01T15:00:00Z",
                "requested_snapshot_at": "2025-01-01T16:00:00Z",
                "bookmaker_key": "betclic_fr",
                "market_key": "h2h",
                "outcome_name": "Home",
                "price": 2.0,
            }
        ]
    )
    failed = build_evidence_quality_report(
        plan={"bookmakers": ["betclic_fr"], "max_credits": 20},
        state={"status": "completed", "completed": [1], "consumed_credits": 1},
        odds_rows=corrupt,
        events=pd.DataFrame([{"event_id": "event-1"}]),
        campaign_plan={"baseline": "consensus", "target_stage": 30, "max_credits": 20},
    )
    assert failed["gates"]["technical_integrity"]["status"] == "FAIL"
    assert failed["decision_gate"]["status"] == "FAIL"


def test_partial_discovery_checkpoint_can_be_restored(tmp_path: Path, monkeypatch, capsys) -> None:
    import scripts.restore_campaign_state as restore

    current_root = tmp_path / "current"
    artifact_root = tmp_path / "artifact"
    plan = {
        "app_version": "4.1.3",
        "campaign_key": "CPK-ONE",
        "target_stage": 30,
        "baseline": "consensus",
        "max_credits": 350,
        "start_date": "2023-01-01",
        "end_date": "2026-07-31",
        "source_commit": "abc123",
    }
    (current_root / "artifacts").mkdir(parents=True)
    (artifact_root / "artifacts").mkdir(parents=True)
    (artifact_root / "data" / "odds_api" / "campaign").mkdir(parents=True)
    (current_root / "artifacts" / "evidence_campaign_plan_v4.json").write_text(json.dumps(plan), encoding="utf-8")
    (artifact_root / "artifacts" / "evidence_campaign_plan_v4.json").write_text(json.dumps(plan), encoding="utf-8")
    (artifact_root / "data" / "odds_api" / "campaign" / "event_discovery_state.json").write_text(
        json.dumps({"status": "in_progress", "completed_call_numbers": [1], "consumed_credits": 1}),
        encoding="utf-8",
    )
    (artifact_root / "data" / "odds_api" / "campaign" / "events_all.csv").write_text(
        "event_id\nevent-a\n", encoding="utf-8"
    )

    monkeypatch.setattr(restore, "ROOT", current_root)
    monkeypatch.setattr(
        sys,
        "argv",
        ["restore_campaign_state", "--artifact-root", str(artifact_root)],
    )
    assert restore.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["restored"] is True
    assert payload["discovery_complete"] is False
    assert payload["backfill_ready"] is False
    assert (current_root / "data" / "odds_api" / "campaign" / "events_all.csv").exists()


def test_campaign_workflow_supports_partial_resume_and_explicit_uncertain_retry() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run-evidence-campaign.yml").read_text(
        encoding="utf-8"
    )
    assert "retry_uncertain_discovery:" in workflow
    assert "steps.restore_checkpoint.outputs.discovery_complete != 'true'" in workflow
    assert "steps.restore_checkpoint.outputs.backfill_ready != 'true'" in workflow
    assert "ARGS+=(--retry-uncertain)" in workflow
    assert "actions: read" in workflow
    assert "Build no-events HOLD report" in workflow
