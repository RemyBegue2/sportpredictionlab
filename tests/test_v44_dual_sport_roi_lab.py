from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import webapp
from sports_predictor.roi_lab import (
    SignalPolicy,
    build_roi_lab_report,
    extract_settled_opportunities,
    optimise_signal_policy,
    simulate_bankroll,
    score_roi_meta_model,
    train_roi_meta_model,
)
from sports_predictor.shadow_mode import evaluate_tennis_shadow


client = TestClient(webapp.app)


def _shadow_row(index: int, *, sport: str = "football", won: bool = True) -> dict:
    date = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    if sport == "football":
        fixture = {"home_team": "Home", "away_team": "Away"}
        probabilities = {"home": 0.65, "draw": 0.15, "away": 0.20}
        selections = [
            {
                "selection": "Home", "decimal_odds": 2.0, "model_probability": 0.65,
                "market_probability": 0.50, "edge": 0.15, "robust_expected_return": 0.20,
            },
            {
                "selection": "Away", "decimal_odds": 3.0, "model_probability": 0.20,
                "market_probability": 0.33, "edge": -0.13, "robust_expected_return": -0.45,
            },
        ]
        result_class = "home" if won else "away"
    else:
        fixture = {"player_1": "Player One", "player_2": "Player Two"}
        probabilities = {"player_1": 0.65, "player_2": 0.35}
        selections = [
            {
                "selection": "Player One", "decimal_odds": 1.9, "model_probability": 0.65,
                "market_probability": 0.53, "edge": 0.12, "robust_expected_return": 0.14,
            },
            {
                "selection": "Player Two", "decimal_odds": 2.1, "model_probability": 0.35,
                "market_probability": 0.47, "edge": -0.12, "robust_expected_return": -0.30,
            },
        ]
        result_class = "player_1" if won else "player_2"
    return {
        "provider_event_id": f"event-{index}",
        "sport": sport,
        "commence_time": date.isoformat(),
        "fixture": fixture,
        "probabilities": probabilities,
        "market_analysis": {"shortlist": [selections[0]["selection"]], "selections": selections},
        "decision": "candidat recherche",
        "status": "settled",
        "temporal_valid": True,
        "evaluation": {"result_class": result_class},
    }


def test_tennis_shadow_evaluation_supports_simulated_return():
    evaluation = evaluate_tennis_shadow(
        fixture={"player_1": "A", "player_2": "B"},
        probabilities={"player_1": 0.7, "player_2": 0.3},
        market_analysis={
            "shortlist": ["A"],
            "selections": [{"selection": "A", "decimal_odds": 1.8}],
        },
        decision="candidat recherche",
        player_1_score=2,
        player_2_score=0,
    )
    assert evaluation["result_class"] == "player_1"
    assert evaluation["correct_top_pick"] is True
    assert evaluation["theoretical_unit_return"] == 0.8
    assert evaluation["rps"] is None


def test_roi_lab_extracts_both_sports_and_simulates_bankroll():
    rows = [_shadow_row(0, sport="football", won=True), _shadow_row(1, sport="tennis", won=False)]
    opportunities = extract_settled_opportunities(rows)
    assert {row.sport for row in opportunities} == {"football", "tennis"}
    simulation = simulate_bankroll(
        opportunities,
        policy=SignalPolicy(minimum_edge=0.03, minimum_robust_return=0.02),
        starting_bankroll=1000,
        strategy="flat_1pct",
    )
    assert simulation.bets == 2
    assert simulation.turnover > 0
    assert simulation.maximum_drawdown >= 0


def test_roi_policy_optimizer_uses_chronological_holdout():
    rows = [_shadow_row(index, won=(index % 5 != 0)) for index in range(50)]
    opportunities = extract_settled_opportunities(rows)
    result = optimise_signal_policy(opportunities)
    assert result["status"] == "candidate"
    assert result["cross_validation"]["candidate_policies_evaluated"] == 144
    assert result["holdout"]["bets"] >= 5
    assert result["holdout_dates"][0] > result["development_dates"][1]



def test_roi_meta_model_trains_on_chronological_holdout():
    rows = [_shadow_row(index, sport=("tennis" if index % 2 else "football"), won=(index % 4 != 0)) for index in range(80)]
    opportunities = extract_settled_opportunities(rows)
    result = train_roi_meta_model(opportunities)
    assert result["status"] == "candidate"
    # One decision row per event: mutually exclusive football/tennis outcomes
    # must not inflate the chronological holdout size.
    assert result["holdout"]["rows"] == 16
    assert 0 <= result["holdout"]["brier"] <= 1
    assert len(result["portable_parameters"]["coef"]) == 6



def test_portable_roi_meta_model_scores_without_loading_arbitrary_artifact():
    probability = score_roi_meta_model(
        model_probability=0.58,
        market_probability=0.50,
        edge=0.08,
        robust_expected_return=0.06,
        decimal_odds=2.0,
        sport="football",
        meta_model={
            "status": "candidate",
            "portable_parameters": {
                "scaler_mean": [0, 0, 0, 0, 0, 0],
                "scaler_scale": [1, 1, 1, 1, 1, 1],
                "coef": [0, 0, 0, 0, 0, 0],
                "intercept": 0.8472978604,
            },
        },
    )
    assert probability is not None
    assert abs(probability - 0.7) < 1e-6

def test_roi_report_refuses_profitability_claim_on_small_sample():
    report = build_roi_lab_report([_shadow_row(index) for index in range(5)])
    assert report["optimisation"]["status"] == "not_evaluable"
    assert report["constraints"]["historical_roi_is_not_a_profitability_claim"] is True
    assert report["constraints"]["automatic_bet_placement"] is False


def test_research_lab_get_never_requires_provider(monkeypatch):
    monkeypatch.setattr(webapp, "latest_benchmark_run", lambda sport_key=None: None)
    monkeypatch.setattr(webapp, "recent_shadow_predictions", lambda *args, **kwargs: [])
    body = client.get("/api/research-lab").json()
    assert body["summary"]["credits_consumed"] == 0
    assert body["constraints"]["automatic_bet_placement"] is False


def test_research_refresh_requires_explicit_credit_firewall(monkeypatch):
    monkeypatch.setattr(webapp, "SETTINGS", replace(webapp.SETTINGS, daily_odds_enabled=False, daily_odds_max_credits=0))
    response = client.post("/api/research-lab/refresh", json={
        "max_credits": 3,
        "tennis_limit": 2,
        "tennis_sport_keys": [],
        "confirmation": "CAPTURE_DAILY_MARKET",
    })
    assert response.status_code == 409
    assert "DAILY_ODDS_ENABLED" in response.text


def test_research_refresh_combines_football_tennis_and_respects_cap(monkeypatch):
    monkeypatch.setattr(
        webapp, "SETTINGS",
        replace(
            webapp.SETTINGS,
            daily_odds_enabled=True,
            daily_odds_max_credits=3,
            daily_tennis_max_tournaments=2,
            shadow_enabled=True,
        ),
    )
    football_event = {
        "event_id": "football-1", "sport_key": "soccer_epl", "commence_time": "2026-08-03T18:00:00Z",
        "api_home_team": "Arsenal", "api_away_team": "Chelsea", "model_home_team": "Arsenal",
        "model_away_team": "Chelsea", "model": {"sport": "football", "market_eligible": True},
        "market_analysis": {
            "shortlist": ["Arsenal"],
            "selections": [{
                "selection": "Arsenal", "decimal_odds": 2.0, "model_probability": 0.58,
                "market_probability": 0.50, "edge": 0.08, "robust_expected_return": 0.06,
            }],
        },
    }
    tennis_event = {
        "event_id": "tennis-1", "sport_key": "tennis_atp_test", "commence_time": "2026-08-03T20:00:00Z",
        "api_player_1": "A", "api_player_2": "B", "model_player_1": "A", "model_player_2": "B",
        "model": {"sport": "tennis", "model_mode": "calibrated_model", "market_eligible": True},
        "market_analysis": {
            "shortlist": ["A"],
            "selections": [{
                "selection": "A", "decimal_odds": 1.9, "model_probability": 0.62,
                "market_probability": 0.53, "edge": 0.09, "robust_expected_return": 0.05,
            }],
        },
    }
    monkeypatch.setattr(webapp, "_football_odds_slate", lambda *args, **kwargs: {
        "events": [football_event], "summary": {"events": 1}, "from_cache": False,
        "quota": {"last_cost": 1},
    })
    monkeypatch.setattr(webapp, "_active_tennis_sports", lambda **kwargs: [
        {"key": "tennis_atp_test", "title": "ATP Test"},
        {"key": "tennis_wta_test", "title": "WTA Test"},
    ])
    calls = []
    def tennis_slate(key, surface, **kwargs):
        calls.append((key, surface))
        return {
            "sport_key": key, "surface": surface, "events": [tennis_event] if not calls[:-1] else [],
            "summary": {"events": 1}, "from_cache": False, "quota": {"last_cost": 1},
        }
    monkeypatch.setattr(webapp, "_tennis_odds_slate", tennis_slate)
    monkeypatch.setattr(webapp, "settle_shadow_predictions", lambda: {"settled": 0, "skipped": 0})
    monkeypatch.setattr(webapp, "recent_shadow_predictions", lambda *args, **kwargs: [])
    monkeypatch.setattr(webapp, "record_benchmark_run", lambda **kwargs: 77)

    response = client.post("/api/research-lab/refresh", json={
        "date": "2026-08-03",
        "max_credits": 3,
        "tennis_limit": 2,
        "tennis_sport_keys": [],
        "confirmation": "CAPTURE_DAILY_MARKET",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["credits_consumed"] == 3
    assert body["summary"]["football_matches"] == 1
    assert body["summary"]["tennis_matches"] == 1
    assert body["summary"]["experimental_signals"] == 2
    assert body["run"]["id"] == 77
    assert len(calls) == 2


def test_tennis_surface_inference_is_conservative():
    assert webapp._infer_tennis_surface(sport_key="tennis_atp_wimbledon") == "grass"
    assert webapp._infer_tennis_surface(sport_key="tennis_atp_roland_garros") == "clay"
    assert webapp._infer_tennis_surface(sport_key="tennis_atp_cincinnati") == "hard"


def test_research_refresh_requires_shadow_recording_for_paid_calls(monkeypatch):
    monkeypatch.setattr(
        webapp,
        "SETTINGS",
        replace(
            webapp.SETTINGS,
            daily_odds_enabled=True,
            daily_odds_max_credits=3,
            shadow_enabled=False,
        ),
    )
    response = client.post("/api/research-lab/refresh", json={
        "max_credits": 3,
        "tennis_limit": 0,
        "tennis_sport_keys": [],
        "confirmation": "CAPTURE_DAILY_MARKET",
    })
    assert response.status_code == 409
    assert "SHADOW_MODE_ENABLED" in response.text


def test_research_settlement_imports_football_and_tennis_under_cap(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        webapp,
        "SETTINGS",
        replace(webapp.SETTINGS, daily_odds_enabled=True, daily_odds_max_credits=3),
    )
    monkeypatch.setattr(webapp, "due_shadow_events", lambda limit=500: [
        {"sport_key": "soccer_epl", "provider_event_id": "football-1"},
        {"sport_key": "tennis_atp_test", "provider_event_id": "tennis-1"},
    ])

    payloads = {
        "soccer_epl": [{
            "id": "football-1",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-03T18:00:00Z",
            "completed": True,
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "scores": [{"name": "Arsenal", "score": "2"}, {"name": "Chelsea", "score": "1"}],
            "last_update": "2026-08-03T20:00:00Z",
        }],
        "tennis_atp_test": [{
            "id": "tennis-1",
            "sport_key": "tennis_atp_test",
            "commence_time": "2026-08-03T20:00:00Z",
            "completed": True,
            "home_team": "Player A",
            "away_team": "Player B",
            "scores": [{"name": "Player A", "score": "2"}, {"name": "Player B", "score": "0"}],
            "last_update": "2026-08-03T22:00:00Z",
        }],
    }

    class FakeClient:
        def scores(self, sport_key, **kwargs):
            return SimpleNamespace(
                from_cache=False,
                quota=SimpleNamespace(last_cost=1),
                payload=payloads[sport_key],
            )

    monkeypatch.setattr(webapp, "odds_client", lambda: FakeClient())
    persisted = []
    monkeypatch.setattr(webapp, "persist_event_result", lambda **kwargs: persisted.append(kwargs))
    monkeypatch.setattr(webapp, "record_data_quality_issue", lambda **kwargs: None)
    monkeypatch.setattr(webapp, "settle_shadow_predictions", lambda: {"settled": 2, "skipped": 0})
    monkeypatch.setattr(webapp, "recent_shadow_predictions", lambda *args, **kwargs: [])
    monkeypatch.setattr(webapp, "_latest_research_payload", lambda: {
        "summary": {"football_matches": 1, "tennis_matches": 1},
        "constraints": {"automatic_bet_placement": False},
        "errors": [],
    })
    monkeypatch.setattr(webapp, "record_benchmark_run", lambda **kwargs: 88)

    response = client.post("/api/research-lab/settle", json={
        "max_credits": 3,
        "confirmation": "SETTLE_DAILY_MARKET",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["settlement"]["credits_consumed"] == 2
    assert body["settlement"]["results_imported"] == 2
    assert body["settlement"]["settled"] == 2
    assert body["run"]["id"] == 88
    assert {item["provider_event_id"] for item in persisted} == {"football-1", "tennis-1"}


def test_tennis_abstention_can_only_be_rehabilitated_after_sport_specific_meta_holdout():
    event = {
        "event_id": "tennis-meta-1",
        "sport_key": "tennis_atp_test",
        "commence_time": "2026-08-03T20:00:00Z",
        "api_player_1": "Player A",
        "api_player_2": "Player B",
        "model_player_1": "Player A",
        "model_player_2": "Player B",
        "model": {"sport": "tennis", "model_mode": "elo_only_uncalibrated", "market_eligible": False},
        "market_analysis": {
            "shortlist": [],
            "selections": [{
                "selection": "Player A",
                "decimal_odds": 2.0,
                "model_probability": 0.55,
                "market_probability": 0.50,
                "edge": 0.05,
                "robust_expected_return": 0.0,
            }],
        },
    }
    meta = {
        "status": "candidate",
        "sport_event_counts": {"tennis": 30},
        "portable_parameters": {
            "scaler_mean": [0, 0, 0, 0, 0, 0],
            "scaler_scale": [1, 1, 1, 1, 1, 1],
            "coef": [0, 0, 0, 0, 0, 0],
            "intercept": 0.8472978604,
        },
    }
    signal = webapp._safe_current_signal(event, roi_lab={
        "optimisation": {"status": "candidate", "policy": SignalPolicy().to_dict()},
        "meta_model": meta,
    })
    assert signal is not None
    assert signal["status"] == "SHADOW_SIGNAL_META"
    assert signal["sport"] == "tennis"
    assert signal["meta_sport_events"] == 30

    blocked = webapp._safe_current_signal(event, roi_lab={
        "optimisation": {"status": "candidate", "policy": SignalPolicy().to_dict()},
        "meta_model": {**meta, "sport_event_counts": {"tennis": 29}},
    })
    assert blocked is None


def test_browser_smoke_requires_dual_sport_roi_lab_rendering():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "scripts" / "browser_smoke_test.py").read_text(encoding="utf-8")
    assert "dual-sport ROI lab did not render" in source
    assert "#researchSignalCount" in source
    assert "#researchTraining" in source
