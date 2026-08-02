from sports_predictor.backtest import _block_bootstrap_mean_ci
import numpy as np

def test_block_bootstrap_ci_is_ordered():
    lo, hi = _block_bootstrap_mean_ci(np.array([-0.2,-0.1,0.0,-0.05,-0.12]), block_size=2, n_boot=100)
    assert lo <= hi

import pandas as pd
from sports_predictor.backtest import backtest_football, backtest_tennis


class _DummyFootball:
    def fit(self, history):
        assert len(history) >= 30

    def predict_matches(self, history, fixtures):
        assert pd.to_datetime(history["date"], utc=True).max() < pd.to_datetime(fixtures["date"], utc=True).min()
        return [{"away_win": 0.25, "draw": 0.25, "home_win": 0.50} for _ in range(len(fixtures))]


class _DummyTennis:
    def fit(self, history):
        assert len(history) >= 30

    def predict_matches(self, history, fixtures):
        assert pd.to_datetime(history["date"], utc=True).max() < pd.to_datetime(fixtures["date"], utc=True).min()
        return np.full(len(fixtures), 0.55)


def test_football_backtest_batches_same_dates():
    rows = []
    for day in range(12):
        for match in range(4):
            rows.append({
                "date": f"2024-01-{day + 1:02d}", "league": "X",
                "home_team": f"H{match}", "away_team": f"A{match}",
                "home_goals": (day + match) % 3, "away_goals": (day + 2 * match) % 2,
            })
    report = backtest_football(pd.DataFrame(rows), initial_train=32, horizon=8, max_folds=2,
                               model_factory=_DummyFootball)
    assert report["n_predictions"] == 16
    assert "batch" in report["protocol"]


def test_tennis_backtest_batches_tournament_dates():
    rows = []
    for week in range(12):
        for match in range(4):
            rows.append({
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=7 * week),
                "tour": "ATP", "surface": "hard", "tournament_level": "A", "best_of": 3,
                "winner_name": f"W{week}_{match}", "loser_name": f"L{week}_{match}",
                "winner_rank": match + 1, "loser_rank": match + 20,
                "winner_rank_points": 1000 - match, "loser_rank_points": 500 - match,
            })
    report = backtest_tennis(pd.DataFrame(rows), initial_train=32, horizon=8, max_folds=2,
                             model_factory=_DummyTennis)
    assert report["n_predictions"] == 16
    assert "batch" in report["protocol"]
