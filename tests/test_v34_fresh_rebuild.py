from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import dispose_database, init_database, latest_shadow_cycle, record_shadow_cycle, shadow_cycle_lock
from sports_predictor.fresh_rebuild import PromotionPolicy, build_multiseason_dataset, normalize_season_frame, promotion_decision


def test_normalize_public_season_schema_and_aliases() -> None:
    raw = pd.DataFrame({
        "Date": ["2025-08-15", "bad"],
        "HomeTeam": ["Manchester United", "X"],
        "AwayTeam": ["Arsenal", "Y"],
        "FTHG": [2, None],
        "FTAG": [1, None],
    })
    out = normalize_season_frame(raw, season="2025-26", source="fixture.csv")
    assert len(out) == 1
    assert out.iloc[0]["home_team"] == "Man United"
    assert out.iloc[0]["league"] == "E0"
    assert str(out.iloc[0]["season"]) == "2025-26"


def test_multiseason_build_deduplicates(tmp_path: Path) -> None:
    frame = pd.DataFrame({
        "Date": pd.date_range("2024-01-01", periods=120, freq="D").strftime("%Y-%m-%d"),
        "HomeTeam": [f"H{i%20}" for i in range(120)],
        "AwayTeam": [f"A{i%20}" for i in range(120)],
        "FTHG": [i % 4 for i in range(120)],
        "FTAG": [(i + 1) % 3 for i in range(120)],
    })
    one = tmp_path / "epl_2023_24.csv"
    two = tmp_path / "epl_2024_25.csv"
    frame.to_csv(one, index=False)
    frame.assign(Date=pd.date_range("2025-01-01", periods=120, freq="D").strftime("%Y-%m-%d")).to_csv(two, index=False)
    out = build_multiseason_dataset([one, two])
    assert len(out) == 240
    assert out["date"].is_monotonic_increasing
    assert set(out["season"]) == {"2023-24", "2024-25"}


def test_promotion_policy_can_accept_and_reject() -> None:
    dataset = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=100, freq="D")})
    evaluation = {"n_test": 30, "metrics": {"log_loss": 0.9, "naive_log_loss": 1.05, "ece": 0.08}}
    accepted = promotion_decision(
        dataset=dataset, evaluation=evaluation, as_of="2025-05-01",
        policy=PromotionPolicy(minimum_rows=100, minimum_test_rows=30, maximum_age_days=30, maximum_ece=0.1),
    )
    assert accepted.eligible
    rejected = promotion_decision(
        dataset=dataset, evaluation={"n_test": 5, "metrics": {"log_loss": 1.2, "naive_log_loss": 1.0, "ece": 0.3}},
        as_of="2026-05-01", policy=PromotionPolicy(minimum_rows=100, minimum_test_rows=30, maximum_age_days=30),
    )
    assert not rejected.eligible
    assert "fresh_cutoff" in rejected.checks and not rejected.checks["fresh_cutoff"]


def test_shadow_cycle_diagnostics_round_trip(tmp_path: Path) -> None:
    dispose_database()
    settings = CloudSettings(
        environment="test", auth_required=False, app_password=None, session_secret="test-secret",
        cookie_secure=False, database_url=f"sqlite:///{tmp_path/'v34.db'}", odds_sync_sports=("soccer_epl",),
        odds_stale_minutes=15, model_version="3.4.1",
    )
    try:
        init_database(settings)
        with shadow_cycle_lock() as acquired:
            assert acquired
        record_shadow_cycle(
            status="success", sports=["soccer_epl"], events_seen=7, predictions_created=0,
            predictions_reused=0, predictions_settled=0, quota_remaining=490,
            diagnostics={"outside_shadow_horizon": 7}, quota_before=500,
            duration_ms=1234, lock_acquired=True, started_at=datetime.now(timezone.utc),
        )
        cycle = latest_shadow_cycle()
        assert cycle is not None
        assert cycle["diagnostics"]["outside_shadow_horizon"] == 7
        assert cycle["quota_before"] == 500
        assert cycle["duration_ms"] == 1234
    finally:
        dispose_database()
        try:
            import webapp
            init_database(webapp.SETTINGS)
        except Exception:
            pass
