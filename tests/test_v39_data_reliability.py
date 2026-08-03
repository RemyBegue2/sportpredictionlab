from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

from sports_predictor.evidence_quality import build_evidence_quality_report


def _large_events() -> pd.DataFrame:
    start = pd.Timestamp("2023-01-01T15:00:00Z")
    return pd.DataFrame(
        [
            {
                "sport_key": "soccer_epl",
                "event_id": f"event-{index:03d}",
                "commence_time": start + pd.Timedelta(days=index),
                "home_team": f"Home {index}",
                "away_team": f"Away {index}",
            }
            for index in range(111)
        ]
    )


def _odds_for_selected(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    selected = events.head(10)
    for position, event in enumerate(selected.to_dict(orient="records")):
        snapshot = pd.Timestamp(event["commence_time"]) - pd.Timedelta(hours=1)
        bookmakers = ["pinnacle", "betclic_fr"] + (["winamax_fr"] if position < 3 else [])
        for bookmaker in bookmakers:
            for outcome, price in (
                (event["home_team"], 2.1),
                ("Draw", 3.4),
                (event["away_team"], 3.2),
            ):
                rows.append(
                    {
                        **event,
                        "bookmaker_key": bookmaker,
                        "bookmaker_title": bookmaker,
                        "market_key": "h2h",
                        "outcome_name": outcome,
                        "price": price,
                        "requested_snapshot_at": snapshot,
                    }
                )
    return pd.DataFrame(rows)


def test_v39_uses_completed_targets_not_discovered_pool_as_provider_denominator() -> None:
    events = _large_events()
    selected = events.head(10).copy()
    selected["snapshot_at"] = pd.to_datetime(selected["commence_time"], utc=True) - pd.Timedelta(hours=1)
    selected["stage"] = "t-1h"
    requests = selected[["sport_key", "snapshot_at"]].copy()
    requests["request_number"] = range(1, 11)
    matches = pd.DataFrame(
        [
            {
                "provider_event_id": event_id,
                "status": "matched",
                "confidence": 1.0,
            }
            for event_id in selected["event_id"]
        ]
    )
    selection = events[["event_id"]].copy()
    selection["selection_status"] = "not_selected_sample_limit"
    selection.loc[selection.index[:30], "selection_status"] = "not_selected_budget_limit"
    selection.loc[selection.index[:10], "selection_status"] = "selected"

    report = build_evidence_quality_report(
        plan={
            "plan_id": "plan-1",
            "plan_request_id": "REQ-1",
            "available_event_count": 111,
            "requested_event_count": 30,
            "event_count": 10,
            "request_count": 10,
            "target_count": 10,
            "max_credits": 120,
            "bookmakers": ["betclic_fr", "pinnacle", "winamax_fr"],
        },
        state={"status": "completed", "completed": list(range(1, 11)), "consumed_credits": 100},
        odds_rows=_odds_for_selected(events),
        events=events,
        matches=matches,
        requests=requests,
        targets=selected[["sport_key", "event_id", "commence_time", "stage", "snapshot_at"]],
        discovery_state={"status": "completed", "event_count": 111},
        event_selection=selection,
    )

    assert report["funnel"]["discovered_events"] == 111
    assert report["funnel"]["requested_events"] == 30
    assert report["funnel"]["selected_events"] == 10
    assert report["funnel"]["completed_event_snapshots"] == 10
    assert report["funnel"]["provider_returned_event_snapshots"] == 10
    assert report["rates"]["provider_return_coverage"] == 1.0
    assert report["rates"]["event_coverage"] == 1.0
    assert report["rates"]["winamax_coverage"] == 0.3
    assert report["rates"]["consensus_coverage"] == 1.0
    assert report["counts"]["planned_events"] == 10
    assert "event_coverage_below_95_percent" not in report["blockers"]
    assert report["quality_gate"]["status"] == "HOLD"
    assert report["quality_gate"]["accepted"] is False
    assert report["funnel"]["benchmark_ready_events"] == 10
    assert report["gates"]["winamax"]["status"] == "HOLD"
    assert report["gates"]["consensus"]["status"] == "PASS"
    assert report["gates"]["result_matching"]["status"] == "PASS"
    assert sum(report["event_outcome_counts"].values()) == 111


def test_v39_planner_writes_explicit_selection_funnel(tmp_path: Path, monkeypatch) -> None:
    import scripts.plan_historical_backfill as planner

    events = pd.DataFrame(
        [
            {
                "sport_key": "soccer_epl",
                "event_id": f"e{index:02d}",
                "commence_time": pd.Timestamp("2025-01-01T15:00:00Z") + pd.Timedelta(days=index),
                "home_team": f"H{index}",
                "away_team": f"A{index}",
            }
            for index in range(20)
        ]
    )
    events_csv = tmp_path / "events.csv"
    output_dir = tmp_path / "plan"
    events.to_csv(events_csv, index=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_historical_backfill",
            "--events-csv",
            str(events_csv),
            "--horizons",
            "1",
            "--no-closing",
            "--bookmakers",
            "winamax_fr",
            "--max-credits",
            "30",
            "--sample-events",
            "10",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert planner.main() == 0
    summary = json.loads((output_dir / "plan.json").read_text(encoding="utf-8"))
    selection = pd.read_csv(output_dir / "event_selection.csv")
    assert summary["version"] == "4.4.0"
    assert summary["discovered_event_count"] == 20
    assert summary["requested_event_count"] == 10
    assert summary["selected_event_count"] == 3
    assert summary["not_selected_sample_limit"] == 10
    assert summary["not_selected_budget_limit"] == 7
    assert selection["selection_status"].value_counts().to_dict() == {
        "not_selected_sample_limit": 10,
        "not_selected_budget_limit": 7,
        "selected": 3,
    }


def test_v39_zero_credit_recompute_workflow_and_frontend_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "recompute-latest-evidence.yml").read_text(encoding="utf-8")
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "app.js").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "historical-sample-evidence-" in workflow
    assert "Provider API calls executed: **0**" in workflow
    assert "THE_ODDS_API_KEY" not in workflow
    assert "scripts.build_evidence_report" in workflow
    assert "evidence_report_v3_9.json" in workflow
    for element_id in (
        "evidenceIntegrity",
        "evidenceMatching",
        "evidenceConsensus",
        "evidenceStatistical",
        "evidenceFunnel",
        "evidenceBookmakers",
    ):
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js
    assert "app.js?v=4.4.0" in html
