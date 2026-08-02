from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sports_predictor.backfill_control import build_plan_identity, execution_gate, validate_plan_bundle
from sports_predictor.champion_challenger import (
    DecisionPolicy,
    build_model_decision,
    evaluate_promotion_gates,
    run_champion_challenger,
)
from sports_predictor.database import latest_model_decision, record_model_decision
from sports_predictor.market_benchmark import BenchmarkPolicy
from sports_predictor.release_registry import APP_VERSION


def _benchmark_frame(rows: int = 90) -> pd.DataFrame:
    start = pd.Timestamp("2024-01-01", tz="UTC")
    records: list[dict] = []
    for i in range(rows):
        commence = start + pd.Timedelta(days=i)
        result = i % 3
        # Outcome order is away, draw, home. Champion is deliberately sharper
        # than consensus while remaining a valid probability vector.
        champion = np.full(3, 0.20)
        champion[result] = 0.60
        challenger = np.full(3, 0.30)
        challenger[result] = 0.40
        consensus = np.full(3, 0.25)
        consensus[result] = 0.50
        winamax = np.full(3, 0.27)
        winamax[result] = 0.46
        records.append({
            "event_id": f"event-{i}",
            "result_class": result,
            "commence_time": commence,
            "prediction_created_at": commence - pd.Timedelta(hours=2),
            "odds_observed_at": commence - pd.Timedelta(hours=2, minutes=5),
            "result_available_at": commence + pd.Timedelta(hours=3),
            "horizon": "t-1h",
            "taken_odds": 2.10,
            "closing_odds": 2.00,
            "model_away": champion[0],
            "model_draw": champion[1],
            "model_home": champion[2],
            "elo_away": challenger[0],
            "elo_draw": challenger[1],
            "elo_home": challenger[2],
            "consensus_away": consensus[0],
            "consensus_draw": consensus[1],
            "consensus_home": consensus[2],
            "winamax_away": winamax[0],
            "winamax_draw": winamax[1],
            "winamax_home": winamax[2],
        })
    return pd.DataFrame(records)


def test_champion_challenger_uses_identical_temporal_protocol() -> None:
    report = run_champion_challenger(
        _benchmark_frame(),
        contenders=["model", "elo"],
        benchmark_policy=BenchmarkPolicy(
            minimum_predictions=40,
            exploratory_predictions=20,
            minimum_train=30,
            n_folds=3,
            bootstrap_samples=100,
            block_size=5,
        ),
    )
    assert report["contenders"] == ["model", "elo"]
    assert [row["contender"] for row in report["leaderboard"]] == ["model", "elo"]
    assert report["leaderboard"][0]["log_loss"] < report["leaderboard"][1]["log_loss"]
    assert report["reports"]["model"]["temporal_audit"]["rejected_rows"] == 0
    assert report["reports"]["model"]["evaluated_rows"] == report["reports"]["elo"]["evaluated_rows"]


def test_promotion_gates_require_history_live_stability_calibration_and_clv() -> None:
    contender = {
        "evaluated_rows": 1200,
        "ci95_high": -0.002,
        "ece": 0.03,
        "consensus_ece": 0.035,
        "fold_stability": {"favorable_ratio": 0.8},
        "closing_line_value": {"median_log_clv": 0.01},
        "temporal_audit": {"rejected_rows": 0},
    }
    policy = DecisionPolicy(minimum_historical=1000, minimum_live=200)
    passed = evaluate_promotion_gates(contender, live_settled=220, policy=policy)
    assert passed["status"] == "promotion_review"
    assert all(gate["passed"] for gate in passed["gates"].values())
    blocked = evaluate_promotion_gates(contender, live_settled=20, policy=policy)
    assert blocked["status"] == "continue_shadow"
    assert blocked["automatic_promotion"] is False
    assert blocked["profitability_claim"] is False


def test_model_decision_is_deterministic_and_never_auto_promotes() -> None:
    report = run_champion_challenger(
        _benchmark_frame(60),
        contenders=["model", "elo"],
        benchmark_policy=BenchmarkPolicy(minimum_train=20, n_folds=2, bootstrap_samples=50, block_size=5),
    )
    decision = build_model_decision(
        report,
        shadow_summary={"aggregate": {"settled_predictions": 12}},
        champion="model",
        policy=DecisionPolicy(exploratory_historical=20, minimum_historical=50, minimum_live=20),
    )
    assert decision["status"] in {"continue_shadow", "no_go", "promotion_review"}
    assert decision["automatic_promotion"] is False
    assert decision["profitability_claim"] is False
    assert decision["leaderboard"][0]["contender"] == "model"


def test_backfill_plan_is_immutable_and_full_mode_requires_exact_approval(tmp_path: Path) -> None:
    requests = pd.DataFrame({
        "sport_key": ["soccer_epl", "soccer_epl"],
        "snapshot_at": ["2026-08-01T12:00:00Z", "2026-08-02T12:00:00Z"],
        "request_number": [1, 2],
    })
    targets = pd.DataFrame({
        "sport_key": ["soccer_epl", "soccer_epl"],
        "event_id": ["a", "b"],
        "commence_time": ["2026-08-01T13:00:00Z", "2026-08-02T13:00:00Z"],
        "stage": ["t-1h", "t-1h"],
        "snapshot_at": ["2026-08-01T12:00:00Z", "2026-08-02T12:00:00Z"],
    })
    summary = {
        "sport_keys": ["soccer_epl"],
        "markets": ["h2h"],
        "bookmakers": ["winamax_fr"],
        "estimated_credits": 10,
        "event_count": 40,
    }
    summary.update(build_plan_identity(summary, requests, targets))
    requests.to_csv(tmp_path / "requests.csv", index=False)
    targets.to_csv(tmp_path / "targets.csv", index=False)
    (tmp_path / "plan.json").write_text(json.dumps(summary), encoding="utf-8")
    loaded, loaded_requests, loaded_targets = validate_plan_bundle(tmp_path)
    assert loaded["plan_id"] == summary["plan_id"]
    assert len(loaded_requests) == 2 and len(loaded_targets) == 2
    denied = execution_gate(summary, max_credits=10)
    assert denied.allowed is False and denied.approval_required is True
    approved = execution_gate(summary, max_credits=10, approval_plan_id=summary["plan_id"])
    assert approved.allowed is True and approved.mode == "full"
    requests.loc[0, "snapshot_at"] = "2026-08-01T11:55:00Z"
    requests.to_csv(tmp_path / "requests.csv", index=False)
    try:
        validate_plan_bundle(tmp_path)
    except RuntimeError as exc:
        assert "integrity mismatch" in str(exc)
    else:
        raise AssertionError("Tampered backfill plan was accepted")


def test_model_decision_endpoint_and_persistence() -> None:
    import webapp

    decision = {
        "status": "continue_shadow",
        "reason": "test evidence",
        "automatic_promotion": False,
        "profitability_claim": False,
    }
    record_id = record_model_decision(
        sport_key="soccer_epl",
        champion="model",
        decision=decision,
        benchmark_run_id=None,
    )
    latest = latest_model_decision("soccer_epl")
    assert latest and latest["id"] == record_id
    with TestClient(webapp.app) as client:
        response = client.get("/api/model-decision")
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision"]["automatic_promotion"] is False
        assert payload["decision"]["profitability_claim"] is False
        assert payload["persisted"] is not None
        health = client.get("/api/health").json()
        assert health["version"] == APP_VERSION


def test_frontend_exposes_decision_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "static/index.html").read_text(encoding="utf-8")
    js = (root / "static/app.js").read_text(encoding="utf-8")
    assert 'id="decision"' in html
    assert 'id="decisionLeaderboard"' in html
    assert 'id="decisionGates"' in html
    assert "/api/model-decision" in js
    assert "renderDecision" in js
    assert f"app.js?v={APP_VERSION}" in html


def test_live_shadow_records_market_consensus_and_blend_contenders() -> None:
    import webapp
    from sports_predictor.database import recent_shadow_predictions

    now = datetime.now(timezone.utc)
    prediction = {
        "sport": "football",
        "model_version": "champion-test-v1",
        "fixture": {"home_team": "Arsenal", "away_team": "Chelsea", "date": (now + timedelta(days=1)).date().isoformat()},
        "probabilities": {"home": 0.50, "draw": 0.30, "away": 0.20},
        "market_analysis": None,
    }
    winamax = {
        "probabilities": {"Arsenal": 0.45, "Draw": 0.30, "Chelsea": 0.25},
    }
    consensus = {
        "probabilities": {"Arsenal": 0.43, "Draw": 0.31, "Chelsea": 0.26},
    }
    records = webapp._record_football_contenders(
        prediction=prediction,
        event_id="v36-contender-test-event",
        sport_key="soccer_epl",
        commence_time=now + timedelta(minutes=50),
        observed_at=now - timedelta(minutes=1),
        data_cutoff=now - timedelta(days=30),
        api_home="Arsenal",
        api_away="Chelsea",
        winamax=winamax,
        consensus=consensus,
    )
    assert set(records) == {"winamax", "consensus", "blend"}
    rows = [row for row in recent_shadow_predictions(100) if row["provider_event_id"] == "v36-contender-test-event"]
    assert {row["model_id"] for row in rows} == {
        "market-winamax-baseline",
        "market-consensus-baseline",
        "football-consensus-blend",
    }
    blend = next(row for row in rows if row["model_id"] == "football-consensus-blend")
    assert blend["probabilities"]["home"] == pytest.approx(0.465)
    assert blend["decision"] == "benchmark_only"


def test_benchmark_summary_understands_champion_challenger_reports() -> None:
    from sports_predictor.market_benchmark import benchmark_summary

    report = run_champion_challenger(
        _benchmark_frame(60),
        contenders=["model", "elo"],
        benchmark_policy=BenchmarkPolicy(minimum_train=20, n_folds=2, bootstrap_samples=50, block_size=5),
    )
    summary = benchmark_summary(report)
    assert summary["mode"] == "champion_challenger"
    assert summary["selected_contender"] == "model"
    assert summary["contender_count"] == 2
    assert summary["evaluated_rows"] > 0
