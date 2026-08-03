from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import webapp
from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import (
    create_backfill_job,
    database_summary,
    dispose_database,
    init_database,
    latest_benchmark_run,
    persist_event_result,
    persist_odds_rows,
    recent_backfill_jobs,
    recent_data_quality_issues,
    record_benchmark_run,
    record_data_quality_issue,
)
from sports_predictor.event_matching import match_events_to_results
from sports_predictor.market_benchmark import BenchmarkPolicy, run_market_benchmark, temporal_integrity_audit
from sports_predictor.odds_data import bookmaker_h2h_markets, normalize_scores_payload


def _settings(path: Path) -> CloudSettings:
    return CloudSettings(
        environment="test",
        auth_required=False,
        app_password=None,
        session_secret="s" * 48,
        cookie_secure=False,
        database_url=f"sqlite:///{path}",
        odds_sync_sports=("soccer_epl",),
        odds_stale_minutes=15,
        model_version="3.2-test",
    )


def _benchmark_frame(n: int = 260) -> pd.DataFrame:
    rows = []
    for i in range(n):
        result = i % 3
        model = ([0.62, 0.23, 0.15] if result == 0 else [0.18, 0.62, 0.20] if result == 1 else [0.14, 0.22, 0.64])
        winamax = ([0.46, 0.30, 0.24] if result == 0 else [0.28, 0.43, 0.29] if result == 1 else [0.23, 0.30, 0.47])
        consensus = ([0.50, 0.29, 0.21] if result == 0 else [0.25, 0.48, 0.27] if result == 1 else [0.20, 0.28, 0.52])
        commence = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=i)
        rows.append({
            "event_id": f"e-{i}",
            "commence_time": commence,
            "prediction_created_at": commence - pd.Timedelta(hours=1),
            "odds_observed_at": commence - pd.Timedelta(hours=1, minutes=2),
            "result_available_at": commence + pd.Timedelta(hours=3),
            "result_class": result,
            "model_away": model[0], "model_draw": model[1], "model_home": model[2],
            "winamax_away": winamax[0], "winamax_draw": winamax[1], "winamax_home": winamax[2],
            "consensus_away": consensus[0], "consensus_draw": consensus[1], "consensus_home": consensus[2],
        })
    return pd.DataFrame(rows)


def test_event_matching_uses_identity_and_time_without_silent_guessing():
    results = pd.DataFrame([
        {"date": "2025-01-01T15:00:00Z", "home_team": "Manchester City", "away_team": "Arsenal", "home_goals": 2, "away_goals": 1},
        {"date": "2025-01-03T15:00:00Z", "home_team": "Manchester City", "away_team": "Arsenal", "home_goals": 1, "away_goals": 1},
    ])
    events = pd.DataFrame([{"event_id": "evt", "commence_time": "2025-01-01T15:10:00Z", "home_team": "Man City", "away_team": "Arsenal"}])
    mapping = match_events_to_results(events, results)
    assert mapping.iloc[0]["status"] == "matched"
    assert mapping.iloc[0]["result_index"] == 0
    assert mapping.iloc[0]["confidence"] > 0.95


def test_temporal_audit_rejects_odds_after_prediction():
    frame = _benchmark_frame(5)
    frame.loc[2, "odds_observed_at"] = frame.loc[2, "prediction_created_at"] + pd.Timedelta(minutes=1)
    accepted, audit = temporal_integrity_audit(frame)
    assert len(accepted) == 4
    assert audit.rejected_rows == 1
    assert audit.violations["odds_after_prediction"] == 1


def test_market_benchmark_uses_expanding_folds_and_conservative_verdict():
    report = run_market_benchmark(
        _benchmark_frame(),
        policy=BenchmarkPolicy(
            minimum_predictions=100,
            exploratory_predictions=50,
            n_folds=4,
            minimum_train=100,
            bootstrap_samples=100,
            block_size=8,
        ),
    )
    assert report["evaluated_rows"] == 160
    assert len(report["folds"]) == 4
    assert report["comparisons"]["model_vs_winamax"]["ci95_high"] < 0
    assert report["verdict"]["status"] == "preliminary_go"
    assert all(0 <= fold["blend_model_weight"] <= 1 for fold in report["folds"])


def test_historical_market_normalization_keeps_snapshots_separate():
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for minute, prices in [(0, [2.0, 3.5, 4.0]), (5, [1.9, 3.6, 4.2])]:
        snapshot = base + timedelta(minutes=minute)
        for name, price in zip(["Arsenal", "Draw", "Chelsea"], prices, strict=True):
            rows.append({
                "event_id": "evt", "sport_key": "soccer_epl", "commence_time": base + timedelta(days=1),
                "home_team": "Arsenal", "away_team": "Chelsea", "bookmaker_key": "winamax_fr", "bookmaker_title": "Winamax",
                "market_key": "h2h", "outcome_name": name, "price": price, "market_last_update": snapshot,
                "snapshot_time": snapshot, "requested_snapshot_at": snapshot,
            })
    markets = bookmaker_h2h_markets(pd.DataFrame(rows))
    assert len(markets) == 2
    assert markets[0]["odds"]["Arsenal"] != markets[1]["odds"]["Arsenal"]


def test_scores_normalization_and_new_database_records(tmp_path):
    settings = _settings(tmp_path / "v32.db")
    dispose_database()
    try:
        init_database(settings)
        odds = pd.DataFrame([{
            "event_id": "evt-result", "sport_key": "soccer_epl", "commence_time": "2026-08-01T15:00:00Z",
            "home_team": "Arsenal", "away_team": "Chelsea", "bookmaker_key": "winamax_fr", "bookmaker_title": "Winamax",
            "bookmaker_last_update": "2026-08-01T12:00:00Z", "market_key": "h2h", "market_last_update": "2026-08-01T12:00:00Z",
            "outcome_name": "Arsenal", "price": 2.1, "point": None, "snapshot_time": "2026-08-01T12:00:00Z",
        }])
        persist_odds_rows(odds, fetched_at="2026-08-01T12:01:00Z", sport_key="soccer_epl")
        payload = [{
            "id": "evt-result", "sport_key": "soccer_epl", "commence_time": "2026-08-01T15:00:00Z", "completed": True,
            "home_team": "Arsenal", "away_team": "Chelsea", "last_update": "2026-08-01T17:00:00Z",
            "scores": [{"name": "Arsenal", "score": "2"}, {"name": "Chelsea", "score": "1"}],
        }]
        scores = normalize_scores_payload(payload)
        assert int(scores.iloc[0]["home_score"]) == 2
        persist_event_result(provider_event_id="evt-result", home_score=2, away_score=1, completed_at="2026-08-01T17:00:00Z")
        record_data_quality_issue(issue_type="test_issue", severity="warning", details={"reason": "test"}, provider_event_id="evt-result")
        job_id = create_backfill_job(sport_key="soccer_epl", plan={"dry_run": True}, request_count=3, estimated_credits=30)
        assert recent_backfill_jobs(1)[0]["id"] == job_id
        report = run_market_benchmark(_benchmark_frame(70), policy=BenchmarkPolicy(minimum_train=30, n_folds=2, exploratory_predictions=20, minimum_predictions=50, bootstrap_samples=50))
        record_benchmark_run(sport_key="soccer_epl", model_version="3.2-test", status="completed", config={}, report=report, summary={"status": "preliminary_go"})
        assert latest_benchmark_run("soccer_epl")["model_version"] == "3.2-test"
        summary = database_summary()
        assert summary["event_results"] == 1
        assert summary["benchmark_runs"] == 1
        assert summary["open_data_quality_issues"] == 1
        assert recent_data_quality_issues(1)[0]["issue_type"] == "test_issue"
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)


def test_benchmark_api_defaults_to_not_run(monkeypatch):
    monkeypatch.setattr(webapp, "latest_benchmark_run", lambda sport_key=None: None)
    response = TestClient(webapp.app).get("/api/benchmark/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["status"] in {"not_run", "not_evaluable"}
    assert "THE_ODDS_API_KEY" not in response.text


def test_benchmark_never_promotes_without_walk_forward_folds():
    report = run_market_benchmark(
        _benchmark_frame(40),
        policy=BenchmarkPolicy(minimum_train=100, n_folds=5, exploratory_predictions=10, minimum_predictions=20, bootstrap_samples=50),
    )
    assert report["folds"] == []
    assert report["verdict"]["status"] == "not_evaluable"


def test_prepare_market_benchmark_builds_complete_wina_consensus_row(monkeypatch):
    import sports_predictor.historical_benchmark as historical

    results = pd.DataFrame([{
        "date": "2025-01-01T15:00:00Z", "league": "E0", "home_team": "Arsenal", "away_team": "Chelsea",
        "home_goals": 2, "away_goals": 0,
    }])
    events = pd.DataFrame([{
        "event_id": "evt-prep", "sport_key": "soccer_epl", "commence_time": "2025-01-01T15:00:00Z",
        "home_team": "Arsenal", "away_team": "Chelsea",
    }])
    prediction = pd.DataFrame([{
        "result_index": 0, "fold": 1, "commence_time": pd.Timestamp("2025-01-01T15:00:00Z"),
        "home_team": "Arsenal", "away_team": "Chelsea", "result_class": 2,
        "model_away": 0.2, "model_draw": 0.25, "model_home": 0.55,
    }])
    monkeypatch.setattr(historical, "generate_football_walkforward_predictions", lambda *args, **kwargs: prediction)
    snapshot = pd.Timestamp("2025-01-01T14:00:00Z")
    odds_rows = []
    for bookmaker, prices in [("winamax_fr", [2.0, 3.5, 4.2]), ("betclic_fr", [2.05, 3.4, 4.1]), ("pinnacle", [2.02, 3.45, 4.15])]:
        for name, price in zip(["Arsenal", "Draw", "Chelsea"], prices, strict=True):
            odds_rows.append({
                "event_id": "evt-prep", "sport_key": "soccer_epl", "commence_time": "2025-01-01T15:00:00Z",
                "home_team": "Arsenal", "away_team": "Chelsea", "bookmaker_key": bookmaker, "bookmaker_title": bookmaker,
                "bookmaker_last_update": "2025-01-01T13:58:00Z", "market_key": "h2h", "market_last_update": "2025-01-01T13:58:00Z",
                "outcome_name": name, "price": price, "point": None, "snapshot_time": snapshot,
                "requested_snapshot_at": snapshot, "stage": "t-1h",
            })
    prepared, mapping, report = historical.prepare_football_market_benchmark(
        results=results,
        provider_events=events,
        odds_rows=pd.DataFrame(odds_rows),
        target_stage="t-1h",
        initial_train=30,
    )
    assert mapping.iloc[0]["status"] == "matched"
    assert report.benchmark_rows == 1
    assert prepared.iloc[0]["result_class"] == 2
    assert abs(prepared.iloc[0][["winamax_away", "winamax_draw", "winamax_home"]].sum() - 1.0) < 1e-10
    assert prepared.iloc[0]["consensus_bookmakers"] == 2
