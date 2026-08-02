from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.database import (
    database_summary,
    due_shadow_events,
    dispose_database,
    init_database,
    list_models,
    persist_event_result,
    persist_odds_rows,
    recent_shadow_predictions,
    record_shadow_prediction,
    register_model,
    settle_shadow_predictions,
    shadow_summary,
)
from sports_predictor.shadow_mode import evaluate_football_shadow, sample_maturity, shadow_horizon, validate_temporal_order


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
        model_version="3.3.0-test",
        shadow_enabled=True,
        shadow_max_events=50,
        shadow_quota_floor=100,
    )


def _analysis() -> dict:
    return {
        "bookmaker": "Winamax via The Odds API",
        "market_type": "1N2",
        "observed_at": "2026-08-10T12:00:00Z",
        "shortlist": ["Arsenal"],
        "selections": [
            {"selection": "Arsenal", "decimal_odds": 2.10, "reasons": ["edge positif"]},
            {"selection": "Match nul", "decimal_odds": 3.40, "reasons": ["aucun edge robuste"]},
            {"selection": "Chelsea", "decimal_odds": 3.80, "reasons": ["aucun edge robuste"]},
        ],
    }


def test_shadow_temporal_validation_and_maturity() -> None:
    valid = validate_temporal_order(
        prediction_created_at="2026-08-10T12:05:00Z",
        odds_observed_at="2026-08-10T12:00:00Z",
        commence_time="2026-08-10T19:00:00Z",
    )
    assert valid.valid is True
    invalid = validate_temporal_order(
        prediction_created_at="2026-08-10T12:00:00Z",
        odds_observed_at="2026-08-10T12:01:00Z",
        commence_time="2026-08-10T19:00:00Z",
    )
    assert invalid.valid is False
    assert "odds_observed_after_prediction" in invalid.issues
    assert sample_maturity(99)["status"] == "anecdotal"
    assert sample_maturity(500)["status"] == "evaluation"
    assert shadow_horizon(prediction_created_at="2026-08-10T18:45:00Z", commence_time="2026-08-10T19:00:00Z") == "pre-close"
    assert shadow_horizon(prediction_created_at="2026-08-10T18:00:00Z", commence_time="2026-08-10T19:00:00Z") == "t-1h"
    assert shadow_horizon(prediction_created_at="2026-08-09T18:59:00Z", commence_time="2026-08-10T19:00:00Z") is None


def test_shadow_record_is_idempotent_and_settles(tmp_path: Path) -> None:
    import webapp

    dispose_database()
    try:
        init_database(_settings(tmp_path / "shadow.db"))
        rows = pd.DataFrame([{
            "event_id": "event-shadow-1",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-10T19:00:00Z",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "bookmaker_key": "winamax_fr",
            "bookmaker_title": "Winamax",
            "bookmaker_last_update": "2026-08-10T12:00:00Z",
            "market_key": "h2h",
            "market_last_update": "2026-08-10T12:00:00Z",
            "outcome_name": "Arsenal",
            "price": 2.10,
            "point": None,
            "snapshot_time": "2026-08-10T12:00:00Z",
        }])
        persist_odds_rows(rows, fetched_at="2026-08-10T12:05:00Z", sport_key="soccer_epl")
        kwargs = dict(
            provider_event_id="event-shadow-1",
            sport_key="soccer_epl",
            sport="football",
            model_id="football-1n2-shadow",
            model_version="3.3.0-test",
            fixture={"home_team": "Arsenal", "away_team": "Chelsea", "date": "2026-08-10"},
            probabilities={"home": 0.52, "draw": 0.28, "away": 0.20},
            market_analysis=_analysis(),
            decision="candidat recherche",
            source="test",
            prediction_created_at="2026-08-10T12:05:00Z",
            commence_time="2026-08-10T19:00:00Z",
            odds_observed_at="2026-08-10T12:00:00Z",
            data_cutoff="2024-05-20T00:00:00Z",
        )
        first = record_shadow_prediction(**kwargs)
        second = record_shadow_prediction(**kwargs)
        assert first["created"] is True
        assert second["created"] is False
        assert first["prediction_hash"] == second["prediction_hash"]
        assert first["horizon"] == "t-24h"

        persist_event_result(
            provider_event_id="event-shadow-1", home_score=2, away_score=1,
            completed_at="2026-08-10T21:00:00Z",
        )
        settled = settle_shadow_predictions()
        assert settled["settled"] == 1
        row = recent_shadow_predictions(1)[0]
        assert row["status"] == "settled"
        assert row["evaluation"]["result_class"] == "home"
        assert row["evaluation"]["theoretical_unit_return"] == 1.10
        summary = shadow_summary(sport_key="soccer_epl")
        assert summary["total_predictions"] == 1
        assert summary["aggregate"]["settled_predictions"] == 1
        assert summary["verdict"]["status"] == "not_evaluable"
        db = database_summary()
        assert db["shadow_predictions"] == 1
        assert db["settled_shadow_predictions"] == 1
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)


def test_invalid_shadow_prediction_is_quarantined(tmp_path: Path) -> None:
    import webapp

    dispose_database()
    try:
        init_database(_settings(tmp_path / "invalid.db"))
        row = record_shadow_prediction(
            provider_event_id="event-invalid", sport_key="soccer_epl", sport="football",
            model_id="football-1n2-shadow", model_version="3.3.0-test",
            fixture={"home_team": "Arsenal", "away_team": "Chelsea"},
            probabilities={"home": 0.5, "draw": 0.3, "away": 0.2}, market_analysis=None,
            decision="abstention", source="test",
            prediction_created_at="2026-08-10T20:00:00Z",
            commence_time="2026-08-10T19:00:00Z",
        )
        assert row["temporal_valid"] is False
        stored = recent_shadow_predictions(1)[0]
        assert stored["status"] == "invalid"
        assert "prediction_at_or_after_event_start" in stored["temporal_issues"]
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)



def test_shadow_horizon_uniqueness_skip_and_due_results(tmp_path: Path) -> None:
    import webapp

    dispose_database()
    try:
        init_database(_settings(tmp_path / "horizons.db"))
        common = dict(
            provider_event_id="event-horizon", sport_key="soccer_epl", sport="football",
            model_id="football-1n2-shadow", model_version="3.3.0-test",
            fixture={"home_team": "Arsenal", "away_team": "Chelsea"},
            probabilities={"home": 0.5, "draw": 0.3, "away": 0.2},
            decision="abstention", source="test", commence_time="2026-08-10T19:00:00Z",
            data_cutoff="2024-05-20T00:00:00Z",
        )
        too_early = record_shadow_prediction(
            **common, market_analysis=None, prediction_created_at="2026-08-09T18:00:00Z",
        )
        assert too_early["skipped"] is True
        first = record_shadow_prediction(
            **common, market_analysis=_analysis(), prediction_created_at="2026-08-10T13:30:00Z",
            odds_observed_at="2026-08-10T13:25:00Z",
        )
        changed_market = dict(_analysis())
        changed_market["observed_at"] = "2026-08-10T13:40:00Z"
        changed_market["selections"] = [dict(x) for x in changed_market["selections"]]
        changed_market["selections"][0]["decimal_odds"] = 2.30
        second = record_shadow_prediction(
            **common, market_analysis=changed_market, prediction_created_at="2026-08-10T13:45:00Z",
            odds_observed_at="2026-08-10T13:40:00Z",
        )
        assert first["created"] is True and first["horizon"] == "t-6h"
        assert second["created"] is False and second["horizon"] == "t-6h"
        due = due_shadow_events(now="2026-08-10T21:00:00Z")
        assert due == [{"provider_event_id": "event-horizon", "sport_key": "soccer_epl"}]
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)

def test_model_registry_upserts(tmp_path: Path) -> None:
    import webapp

    dispose_database()
    try:
        init_database(_settings(tmp_path / "models.db"))
        register_model(
            model_id="football-1n2-shadow", sport="football", version="3.3.0",
            status="shadow", trained_until="2024-05-20", dataset_hash="abc", metrics={"log_loss": 1.0},
        )
        register_model(
            model_id="football-1n2-shadow", sport="football", version="3.3.1",
            status="degraded", trained_until="2024-05-20", dataset_hash="def", metrics={"log_loss": 1.1},
        )
        # Re-registering the same version is idempotent, while a new version remains auditable.
        register_model(
            model_id="football-1n2-shadow", sport="football", version="3.3.1",
            status="shadow", trained_until="2024-05-20", dataset_hash="def", metrics={"log_loss": 1.05},
        )
        models = list_models()
        assert len(models) == 2
        by_version = {model["version"]: model for model in models}
        assert by_version["3.3.0"]["status"] == "shadow"
        assert by_version["3.3.1"]["status"] == "shadow"
        assert by_version["3.3.1"]["metrics"]["log_loss"] == 1.05
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)


def test_single_match_shadow_metrics() -> None:
    result = evaluate_football_shadow(
        fixture={"home_team": "Arsenal", "away_team": "Chelsea"},
        probabilities={"home": 0.5, "draw": 0.3, "away": 0.2},
        market_analysis=_analysis(), decision="candidat recherche", home_score=1, away_score=0,
    )
    assert result["correct_top_pick"] is True
    assert result["theoretical_unit_return"] == 1.10
    assert result["log_loss"] > 0


def test_shadow_api_and_frontend_are_exposed() -> None:
    import webapp

    with TestClient(webapp.app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["version"] == "3.4.4"
        summary = client.get("/api/shadow/summary")
        assert summary.status_code == 200
        assert summary.json()["automatic_bet_placement"] is False
        history = client.get("/api/shadow/predictions?limit=5")
        assert history.status_code == 200

    root = Path(__file__).resolve().parents[1]
    html = (root / "static/index.html").read_text(encoding="utf-8")
    js = (root / "static/app.js").read_text(encoding="utf-8")
    assert "VERSION 3.4" in html
    assert 'id="shadow"' in html
    assert "renderShadow" in js
    assert "app.js?v=3.4.4" in html


def test_stale_football_model_vetoes_market_candidates(monkeypatch) -> None:
    import webapp

    # This test validates the endpoint's stale-model veto, independently of
    # whichever active model the rebuild workflow has just promoted.
    monkeypatch.setattr(
        webapp,
        "_model_freshness",
        lambda **_: {
            "status": "degraded_stale",
            "age_days": 999,
            "stale": True,
            "maximum_age_days": 365,
            "data_cutoff": "2023-10-23T00:00:00+00:00",
        },
    )

    with TestClient(webapp.app) as client:
        response = client.post("/api/football/predict", json={
            "home_team": "Arsenal",
            "away_team": "Man City",
            "date": "2026-08-16",
            "winamax_home_odds": 3.20,
            "winamax_draw_odds": 3.60,
            "winamax_away_odds": 2.20,
            "odds_observed_at": datetime.now(timezone.utc).isoformat(),
        })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model_freshness"]["stale"] is True
    assert payload["market_analysis"]["shortlist"] == []
    assert payload["market_analysis"]["operational_veto"] == "modèle trop ancien pour une sélection opérationnelle"


def test_model_freshness_distinguishes_stale_and_current_cutoffs() -> None:
    import webapp

    stale = webapp._model_freshness(data_cutoff="2023-10-23", as_of="2026-08-16")
    current = webapp._model_freshness(data_cutoff="2026-05-24", as_of="2026-08-16")

    assert stale["stale"] is True
    assert stale["status"] == "degraded_stale"
    assert current["stale"] is False
    assert current["status"] == "current"


def test_shadow_cycle_orchestration_and_quota_guard(monkeypatch, tmp_path: Path) -> None:
    import scripts.run_shadow_cycle as cycle
    import webapp
    from sports_predictor.database import latest_shadow_cycle

    dispose_database()
    settings = _settings(tmp_path / "cycle.db")
    try:
        monkeypatch.setattr(cycle.CloudSettings, "from_env", classmethod(lambda cls, root=None: settings))

        class FakeOddsClient:
            def quota_status(self):
                return {"remaining": 500}

        monkeypatch.setattr(cycle, "odds_client", lambda: FakeOddsClient())
        monkeypatch.setattr(cycle, "_football_odds_slate", lambda *a, **k: {
            "summary": {"events": 3, "shadow_created": 2, "shadow_reused": 1},
            "quota": {"remaining": 499},
        })
        monkeypatch.setattr(cycle, "_sync_results", lambda sports: {"shadow_settled": 1, "quota_remaining": 498})
        monkeypatch.setattr("sys.argv", ["run_shadow_cycle"])
        assert cycle.main() == 0
        last = latest_shadow_cycle()
        assert last is not None
        assert last["status"] == "success"
        assert last["predictions_created"] == 2
        assert last["predictions_settled"] == 1

        low_settings = CloudSettings(**{**settings.__dict__, "shadow_quota_floor": 600})
        monkeypatch.setattr(cycle.CloudSettings, "from_env", classmethod(lambda cls, root=None: low_settings))
        assert cycle.main() == 0
        assert latest_shadow_cycle()["status"] == "skipped_quota"
    finally:
        dispose_database()
        init_database(webapp.SETTINGS)


def test_shadow_auditor_flags_temporal_and_stale_rows() -> None:
    from sports_predictor.audit import audit_shadow_predictions

    findings = audit_shadow_predictions([{
        "provider_event_id": "evt-audit",
        "model_id": "football-1n2-shadow",
        "model_version": "3.3.0",
        "horizon": "t-1h",
        "prediction_created_at": "2026-08-10T20:00:00Z",
        "commence_time": "2026-08-10T19:00:00Z",
        "data_cutoff": "2024-05-20T00:00:00Z",
        "temporal_valid": False,
        "decision": "candidat recherche",
        "market_analysis": None,
    }])
    severities = {(item.role, item.severity) for item in findings}
    assert ("Auditeur anti-fuite", "critical") in severities
    assert ("Trader de cotes", "critical") in severities
    assert ("Ingénieur ML", "high") in severities
