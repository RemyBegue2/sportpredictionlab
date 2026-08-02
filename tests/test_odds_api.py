from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import webapp
from sports_predictor.data_sources.the_odds_api import (
    OddsApiClient,
    OddsApiConfig,
    OddsApiEnvelope,
    QuotaUsage,
)
from sports_predictor.odds_data import bookmaker_h2h_markets, consensus_h2h, devig_market, normalize_odds_payload


class FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {"x-requests-remaining": "999", "x-requests-used": "1", "x-requests-last": "1"}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def sample_payload(now: datetime | None = None):
    current = now or datetime.now(timezone.utc)
    update = current.isoformat().replace("+00:00", "Z")
    commence = (current + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    return [{
        "id": "evt-1",
        "sport_key": "soccer_epl",
        "sport_title": "EPL",
        "commence_time": commence,
        "home_team": "Arsenal",
        "away_team": "Manchester City",
        "bookmakers": [
            {"key": "winamax_fr", "title": "Winamax (FR)", "last_update": update, "markets": [{"key": "h2h", "last_update": update, "outcomes": [
                {"name": "Arsenal", "price": 3.1}, {"name": "Draw", "price": 3.6}, {"name": "Manchester City", "price": 2.2}
            ]}]},
            {"key": "betclic_fr", "title": "Betclic", "last_update": update, "markets": [{"key": "h2h", "last_update": update, "outcomes": [
                {"name": "Arsenal", "price": 3.0}, {"name": "Draw", "price": 3.5}, {"name": "Manchester City", "price": 2.25}
            ]}]},
            {"key": "pinnacle", "title": "Pinnacle", "last_update": update, "markets": [{"key": "h2h", "last_update": update, "outcomes": [
                {"name": "Arsenal", "price": 3.2}, {"name": "Draw", "price": 3.65}, {"name": "Manchester City", "price": 2.18}
            ]}]},
        ],
    }]


def sample_tennis_payload(now: datetime | None = None):
    current = now or datetime.now(timezone.utc)
    update = current.isoformat().replace("+00:00", "Z")
    commence = (current + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    return [{
        "id": "tennis-1",
        "sport_key": "tennis_atp_canadian_open",
        "sport_title": "ATP Canadian Open",
        "commence_time": commence,
        "home_team": "Taylor Fritz",
        "away_team": "Alexander Zverev",
        "bookmakers": [
            {"key": "winamax_fr", "title": "Winamax (FR)", "last_update": update, "markets": [{"key": "h2h", "last_update": update, "outcomes": [
                {"name": "Taylor Fritz", "price": 2.05}, {"name": "Alexander Zverev", "price": 1.78}
            ]}]},
            {"key": "pinnacle", "title": "Pinnacle", "last_update": update, "markets": [{"key": "h2h", "last_update": update, "outcomes": [
                {"name": "Taylor Fritz", "price": 2.08}, {"name": "Alexander Zverev", "price": 1.79}
            ]}]},
        ],
    }]


def test_quota_estimator_groups_bookmakers():
    assert OddsApiClient.estimate_quota_cost(markets=["h2h"], bookmakers=["a"] * 1, historical=True) == 10
    assert OddsApiClient.estimate_quota_cost(markets=["h2h"], bookmakers=[f"b{i}" for i in range(10)], historical=True) == 10
    assert OddsApiClient.estimate_quota_cost(markets=["h2h"], bookmakers=[f"b{i}" for i in range(11)], historical=True) == 20
    assert OddsApiClient.estimate_quota_cost(markets=["h2h", "totals"], bookmakers=["a"], historical=False) == 2


def test_client_never_caches_api_key(tmp_path: Path):
    session = FakeSession(FakeResponse(sample_payload()))
    config = OddsApiConfig(api_key="super-secret", cache_dir=tmp_path)
    client = OddsApiClient(config, session=session)
    result = client.current_odds("soccer_epl", bookmakers=("winamax_fr",))
    assert result.quota.remaining == 999
    files = list(tmp_path.glob("*.json"))
    assert files
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "super-secret" not in combined
    assert session.calls[0][1]["params"]["apiKey"] == "super-secret"


def test_devig_normalization_and_consensus():
    devigged = devig_market(["A", "Draw", "B"], [2.2, 3.4, 3.5])
    assert abs(sum(devigged.probabilities) - 1.0) < 1e-12
    rows = normalize_odds_payload(sample_payload())
    markets = bookmaker_h2h_markets(rows)
    assert len(markets) == 3
    consensus = consensus_h2h(markets, exclude=("winamax_fr",))
    assert consensus is not None
    assert consensus["bookmaker_count"] == 2
    assert abs(sum(consensus["probabilities"].values()) - 1.0) < 1e-12


def test_odds_status_does_not_expose_key(monkeypatch, tmp_path: Path):
    fake = OddsApiClient(OddsApiConfig(api_key="hidden", cache_dir=tmp_path), session=FakeSession(FakeResponse([])))
    monkeypatch.setattr(webapp, "odds_client", lambda: fake)
    body = TestClient(webapp.app).get("/api/odds/status").json()
    assert body["configured"] is True
    assert body["key_exposed_to_frontend"] is False
    assert "hidden" not in json.dumps(body)


def test_live_football_slate_with_fake_provider(monkeypatch, tmp_path: Path):
    now = datetime.now(timezone.utc)

    class FakeClient:
        config = OddsApiConfig(api_key="hidden", cache_dir=tmp_path)

        def current_odds(self, *args, **kwargs):
            return OddsApiEnvelope(
                payload=sample_payload(now),
                quota=QuotaUsage(remaining=500, used=5, last_cost=1),
                fetched_at=now.isoformat(),
                from_cache=False,
                request_fingerprint="abc",
            )

        def quota_status(self):
            return {"known": True, "remaining": 500, "used": 5, "last_cost": 1, "updated_at": now.isoformat()}

    monkeypatch.setattr(webapp, "odds_client", lambda: FakeClient())
    client = TestClient(webapp.app)
    response = client.get("/api/odds/football/slate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["events"] == 1
    assert body["events"][0]["winamax_available"] is True
    assert body["events"][0]["model_away_team"] == "Man City"
    assert len(body["events"][0]["market_analysis"]["selections"]) == 3
    stored = [row for row in webapp.recent_predictions(20) if row.get("provider_event_id") == "evt-1"]
    assert stored
    assert stored[0]["market_analysis"] is not None
    assert len(stored[0]["market_analysis"]["selections"]) == 3
    daily = client.get(f"/api/bets/today?date={(now + timedelta(days=1)).date().isoformat()}")
    assert daily.status_code == 200
    assert daily.json()["source"] == "postgresql"
    assert daily.json()["summary"]["events_reviewed"] >= 1


def test_tennis_slate_and_sport_discovery(monkeypatch, tmp_path: Path):
    now = datetime.now(timezone.utc)

    class FakeClient:
        config = OddsApiConfig(api_key="hidden", cache_dir=tmp_path)
        def current_odds(self, sport_key, *args, **kwargs):
            return OddsApiEnvelope(payload=sample_tennis_payload(now), quota=QuotaUsage(400, 6, 1), fetched_at=now.isoformat(), from_cache=False, request_fingerprint="tennis")
        def list_sports(self, *args, **kwargs):
            return OddsApiEnvelope(payload=[{"key":"tennis_atp_canadian_open","group":"Tennis","title":"ATP Canadian Open","active":True}], quota=QuotaUsage(400, 6, 0), fetched_at=now.isoformat(), from_cache=False, request_fingerprint="sports")
        def quota_status(self):
            return {"known": True, "remaining": 400, "used": 6, "last_cost": 1, "updated_at": now.isoformat()}

    monkeypatch.setattr(webapp, "odds_client", lambda: FakeClient())
    client = TestClient(webapp.app)
    sports = client.get("/api/odds/sports?group=Tennis")
    assert sports.status_code == 200
    assert sports.json()["sports"][0]["key"] == "tennis_atp_canadian_open"
    slate = client.get("/api/odds/tennis/slate?sport_key=tennis_atp_canadian_open&surface=hard")
    assert slate.status_code == 200, slate.text
    event = slate.json()["events"][0]
    assert event["winamax_available"] is True
    assert event["decision"] == "abstention"
    assert any("non calibrée" in reason for reason in event["reasons"])
    stored = [row for row in webapp.recent_predictions(20) if row.get("provider_event_id") == "tennis-1"]
    assert stored
    assert stored[0]["market_analysis"] is not None


def test_live_event_is_never_scored_as_prematch(monkeypatch, tmp_path: Path):
    now = datetime.now(timezone.utc)
    payload = sample_payload(now)
    payload[0]["commence_time"] = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

    class FakeClient:
        config = OddsApiConfig(api_key="hidden", cache_dir=tmp_path)
        def current_odds(self, *args, **kwargs):
            return OddsApiEnvelope(payload=payload, quota=QuotaUsage(100, 1, 1), fetched_at=now.isoformat(), from_cache=False, request_fingerprint="live")
        def quota_status(self):
            return {"known": True, "remaining": 100, "used": 1, "last_cost": 1, "updated_at": now.isoformat()}

    monkeypatch.setattr(webapp, "odds_client", lambda: FakeClient())
    body = TestClient(webapp.app).get("/api/odds/football/slate").json()
    event = body["events"][0]
    assert event["in_play"] is True
    assert event["decision"] == "abstention"
    assert "model" not in event
    assert any("commencé" in reason for reason in event["reasons"])


def test_historical_estimate_endpoint():
    response = TestClient(webapp.app).post("/api/odds/historical/estimate", json={
        "snapshot_count": 12,
        "markets": ["h2h"],
        "bookmakers": ["winamax_fr", "betclic_fr", "unibet_fr"],
        "historical": True,
    })
    assert response.status_code == 200
    assert response.json()["estimated_credits"] == 120


def test_scores_endpoint_and_payload_do_not_expose_key(tmp_path: Path):
    payload = [{
        "id": "score-1", "sport_key": "soccer_epl", "commence_time": "2026-08-01T15:00:00Z", "completed": True,
        "home_team": "Arsenal", "away_team": "Chelsea", "scores": [{"name": "Arsenal", "score": "1"}, {"name": "Chelsea", "score": "0"}],
    }]
    session = FakeSession(FakeResponse(payload, headers={"x-requests-remaining": "20", "x-requests-used": "2", "x-requests-last": "2"}))
    client = OddsApiClient(OddsApiConfig(api_key="score-secret", cache_dir=tmp_path), session=session)
    response = client.scores("soccer_epl", days_from=3)
    assert response.payload[0]["completed"] is True
    assert session.calls[0][0].endswith("/v4/sports/soccer_epl/scores")
    assert session.calls[0][1]["params"]["daysFrom"] == 3
    assert "score-secret" not in "\n".join(path.read_text() for path in tmp_path.glob("*.json"))
