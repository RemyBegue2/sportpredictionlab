from __future__ import annotations

import numpy as np
import pandas as pd

from sports_predictor.odds_backtest import (
    build_historical_plan,
    multiclass_metrics,
    paired_log_loss_difference,
    safe_threshold_gate,
)
from sports_predictor.odds_data import closing_line_value


def test_historical_plan_groups_shared_snapshots():
    events = pd.DataFrame([
        {"sport_key": "soccer_epl", "event_id": "a", "commence_time": "2025-05-10T14:00:00Z"},
        {"sport_key": "soccer_epl", "event_id": "b", "commence_time": "2025-05-10T14:00:00Z"},
    ])
    plan = build_historical_plan(events, horizons_hours=[24, 1], closing_minutes=10)
    assert len(plan.targets) == 6
    assert len(plan.requests) == 3
    assert plan.estimated_credits == 30


def test_market_comparison_metrics_and_clv():
    y = [0, 1, 2, 0]
    model = np.array([[.7,.2,.1],[.2,.6,.2],[.1,.2,.7],[.6,.3,.1]])
    market = np.array([[.6,.25,.15],[.25,.5,.25],[.15,.25,.6],[.5,.35,.15]])
    metrics = multiclass_metrics(y, model, labels=[0,1,2])
    assert metrics["log_loss"] < 1.0
    paired = paired_log_loss_difference(y, model, market, bootstrap_samples=200)
    assert paired["mean_model_minus_market_log_loss"] < 0
    clv = closing_line_value(taken_odds=2.2, closing_odds=2.0)
    assert clv["log_clv"] > 0


def test_conservative_gate():
    assert safe_threshold_gate(edge=.05, lower_confidence_edge=.01)
    assert not safe_threshold_gate(edge=.05, lower_confidence_edge=-.01)
