from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from sports_predictor.betting import analyze_market, analyze_two_way
from webapp import app

client = TestClient(app)


def test_market_devig_and_candidate():
    result = analyze_market(
        labels=["A", "B"],
        model_probabilities=[0.62, 0.38],
        decimal_odds=[1.85, 2.10],
        market_type="winner",
        observed_at="2026-08-02T11:00:00+00:00",
        uncertainty_margin=0.03,
        now=datetime(2026, 8, 2, 11, 15, tzinfo=timezone.utc),
    )
    assert result.overround > 0
    assert abs(sum(x.market_probability for x in result.selections) - 1.0) < 1e-9
    assert "A" in result.shortlist
    assert result.selections[0].status == "candidat recherche"


def test_uncalibrated_market_forces_abstention():
    result = analyze_two_way(
        player_1="A",
        player_2="B",
        player_1_probability=0.70,
        player_1_odds=1.80,
        player_2_odds=2.20,
        observed_at="2026-08-02T11:00:00+00:00",
        calibrated=False,
    )
    assert all(x["status"] == "abstention" for x in result["selections"])
    assert result["shortlist"] == []


def test_invalid_market_inputs():
    with pytest.raises(ValueError):
        analyze_market(
            labels=["A", "B"],
            model_probabilities=[0.70, 0.40],
            decimal_odds=[1.5, 2.5],
            market_type="winner",
        )


def test_daily_slate_endpoint():
    response = client.get("/api/bets/today?date=2026-08-02")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["research_candidates"] == 0
    assert len(body["events"]) == 2
    assert all(x["decision"] == "abstention" for x in body["events"])


def test_football_market_analysis_endpoint():
    response = client.post("/api/football/predict", json={
        "home_team": "Arsenal",
        "away_team": "Man City",
        "date": "2026-08-02",
        "winamax_home_odds": 2.80,
        "winamax_draw_odds": 3.50,
        "winamax_away_odds": 2.55
    })
    assert response.status_code == 200, response.text
    analysis = response.json()["market_analysis"]
    assert len(analysis["selections"]) == 3
    assert analysis["bookmaker"] == "Winamax"
    assert all(x["status"] == "à actualiser" for x in analysis["selections"])


def test_incomplete_odds_rejected():
    response = client.post("/api/football/predict", json={
        "home_team": "Arsenal",
        "away_team": "Man City",
        "winamax_home_odds": 2.8
    })
    assert response.status_code == 422


def test_future_odds_timestamp_rejected():
    with pytest.raises(ValueError, match="future"):
        analyze_market(
            labels=["A", "B"],
            model_probabilities=[0.55, 0.45],
            decimal_odds=[1.9, 2.0],
            market_type="winner",
            observed_at="2026-08-02T12:00:00+00:00",
            now=datetime(2026, 8, 2, 11, 0, tzinfo=timezone.utc),
        )
