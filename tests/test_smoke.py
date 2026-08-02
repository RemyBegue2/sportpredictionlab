import pandas as pd

from sports_predictor.demo_data import make_football_data, make_tennis_data
from sports_predictor.football import FootballPredictor
from sports_predictor.tennis import TennisPredictor


def test_football_smoke():
    df = make_football_data(180)
    model = FootballPredictor()
    ev = model.fit(df)
    assert 0 <= ev.metrics["accuracy"] <= 1
    fixture = pd.DataFrame([{
        "date": df["date"].max() + pd.Timedelta(days=2), "league": "Ligue-1",
        "home_team": "FR_01", "away_team": "FR_02",
    }])
    pred = model.predict_matches(df, fixture)[0]
    assert abs(pred["away_win"] + pred["draw"] + pred["home_win"] - 1) < 1e-8


def test_tennis_smoke():
    df = make_tennis_data(260)
    model = TennisPredictor()
    ev = model.fit(df)
    assert 0 <= ev.metrics["accuracy"] <= 1
    assert ev.metrics["symmetry_error"] < 1e-8
    fixture = pd.DataFrame([{
        "date": df["date"].max() + pd.Timedelta(days=2), "tour": "ATP-demo",
        "surface": "hard", "tournament_level": "A", "best_of": 3,
        "player_1": "Player_001", "player_2": "Player_002",
    }])
    p = float(model.predict_matches(df, fixture)[0])
    assert 0 <= p <= 1
