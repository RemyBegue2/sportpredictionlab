from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
import pytest

import webapp
from sports_predictor.daily_product import (
    DailyFixtureError,
    DailyFixtureSource,
    EspnFixtureSource,
    FootballFixtureSource,
    build_model_diagnostics,
    fixture_identifier,
    probability_diagnostics,
    select_fixture_window,
)
from sports_predictor.identity import football_model_name
from sports_predictor.data_sources.the_odds_api import (
    OddsApiClient,
    OddsApiConfig,
    OddsApiNetworkDisabled,
)


client = TestClient(webapp.app)


def _fixture_csv() -> bytes:
    return (
        "Div,Date,Time,HomeTeam,AwayTeam\n"
        "E0,03/08/2026,23:00,Arsenal,Chelsea\n"
        "E0,05/08/2026,19:45,Liverpool,Man City\n"
        "F1,03/08/2026,18:00,Paris SG,Lille\n"
    ).encode("utf-8")


def test_fixture_feed_normalization_and_window():
    frame = FootballFixtureSource.normalize_csv(_fixture_csv())
    assert list(frame["league"]) == ["F1", "E0", "E0"]
    assert str(frame.iloc[0]["date"].tzinfo) == "UTC"
    selected = select_fixture_window(frame, requested_date="2026-08-03", horizon_days=2, leagues=("E0",))
    assert len(selected) == 2
    assert set(selected["home_team"]) == {"Arsenal", "Liverpool"}
    assert fixture_identifier(selected.iloc[0]) == fixture_identifier(selected.iloc[0])


def test_fixture_identifier_is_stable_across_provider_aliases_and_time_changes():
    espn = {
        "date": "2026-08-23T14:00:00Z",
        "league": "E0",
        "home_team": "Manchester City",
        "away_team": "AFC Bournemouth",
    }
    football_data = {
        "date": "2026-08-23T15:00:00Z",
        "league": "E0",
        "home_team": "Man City",
        "away_team": "Bournemouth",
    }
    assert fixture_identifier(espn) == fixture_identifier(football_data)


def test_current_premier_league_aliases_map_to_model_names():
    assert football_model_name("Leeds United") == "Leeds"
    assert football_model_name("Ipswich Town") == "Ipswich"
    assert football_model_name("Sunderland AFC") == "Sunderland"
    assert football_model_name("Coventry City") == "Coventry"
    assert football_model_name("Hull City") == "Hull"



def test_espn_fixture_payload_normalization():
    payload = {
        "events": [{
            "date": "2026-08-15T14:00:00Z",
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Manchester City"}},
                    {"homeAway": "away", "team": {"displayName": "Wolverhampton Wanderers"}},
                ]
            }],
        }]
    }
    frame = EspnFixtureSource.normalize_payload(payload)
    assert len(frame) == 1
    assert frame.iloc[0]["league"] == "E0"
    assert frame.iloc[0]["home_team"] == "Manchester City"
    assert frame.iloc[0]["fixture_date"] == "2026-08-15"



def test_espn_fetch_uses_one_cached_range_request(tmp_path: Path):
    calls = []

    class Response:
        content = (
            b'{"events":[{"date":"2026-08-15T14:00:00Z","competitions":[{"competitors":'
            b'[{"homeAway":"home","team":{"displayName":"Arsenal"}},'
            b'{"homeAway":"away","team":{"displayName":"Chelsea"}}]}]}]}'
        )

        def raise_for_status(self):
            return None

    class Session:
        headers = {}

        def mount(self, *args, **kwargs):
            return None

        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    source = EspnFixtureSource(tmp_path, session=Session())
    first = source.fetch_window(requested_date="2026-08-15", horizon_days=7)
    second = source.fetch_window(requested_date="2026-08-15", horizon_days=7)
    assert len(first.fixtures) == 1
    assert first.from_cache is False
    assert second.from_cache is True
    assert len(calls) == 1
    assert calls[0][1]["params"]["dates"] == "20260815-20260822"


def test_composite_fixture_source_backs_off_after_total_network_failure(tmp_path: Path):
    network_flags: list[bool] = []

    class FailingEspn:
        def fetch_window(self, **kwargs):
            network_flags.append(bool(kwargs["allow_network"]))
            raise DailyFixtureError("offline")

    class FailingFootballData:
        def fetch(self, **kwargs):
            network_flags.append(bool(kwargs["allow_network"]))
            raise DailyFixtureError("offline")

    source = DailyFixtureSource(tmp_path, failure_backoff_seconds=900)
    source.espn = FailingEspn()
    source.football_data = FailingFootballData()
    with pytest.raises(DailyFixtureError):
        source.fetch_window(requested_date="2026-08-03", horizon_days=31)
    with pytest.raises(DailyFixtureError, match="retry backoff"):
        source.fetch_window(requested_date="2026-08-03", horizon_days=31)
    assert network_flags == [True, True, False, False]


def test_model_diagnostics_blocks_invalid_probability_probe():
    payload = build_model_diagnostics(
        model_loaded=True, artifact_integrity_verified=True, model_version="test",
        data_cutoff="2026-07-01", metrics={"n_test": 200, "log_loss": 1.0, "naive_log_loss": 1.1, "ece": 0.1},
        model_freshness={"stale": False},
        probe_probabilities={"home": 0.7, "draw": 0.5, "away": -0.2},
    )
    assert payload["status"] == "blocked"
    assert "probability_probe_valid" in payload["hard_failures"]


def test_paid_historical_workflows_are_disabled_by_default():
    root = Path(__file__).resolve().parents[1]
    for name in (
        "estimate-evidence-coverage.yml",
        "run-evidence-campaign.yml",
        "run-historical-sample.yml",
    ):
        text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "HISTORICAL_EVIDENCE_ENABLED" in text
        assert "V4.3 credit firewall" in text


def test_probability_diagnostics_rejects_invalid_vector():
    assert probability_diagnostics({"home": 0.5, "draw": 0.25, "away": 0.25})["valid"] is True
    invalid = probability_diagnostics({"home": 0.8, "draw": 0.4, "away": -0.2})
    assert invalid["valid"] is False
    assert "out_of_range_away" in invalid["issues"]


def test_model_diagnostics_distinguishes_product_from_betting_readiness():
    payload = build_model_diagnostics(
        model_loaded=True,
        artifact_integrity_verified=True,
        model_version="test",
        data_cutoff="2026-07-01",
        metrics={"n_test": 200, "log_loss": 1.01, "naive_log_loss": 1.08, "ece": 0.08},
        model_freshness={"stale": False, "age_days": 20},
        probe_probabilities={"home": 0.45, "draw": 0.27, "away": 0.28},
        registry_status="shadow",
    )
    assert payload["status"] == "operational_research"
    assert payload["product_readiness"]["model_only_predictions"] is True
    assert payload["product_readiness"]["market_shortlist"] is False


def test_paid_odds_cache_miss_is_blocked_without_network(tmp_path: Path):
    client = OddsApiClient(OddsApiConfig(api_key="hidden", cache_dir=tmp_path))
    with pytest.raises(OddsApiNetworkDisabled):
        client.current_odds("soccer_epl", allow_network=False)


def test_model_diagnostics_endpoint_is_explicit():
    response = client.get("/api/model-diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"operational_research", "degraded", "blocked"}
    assert body["credit_firewall"]["model_only_cost_credits"] == 0
    assert body["product_readiness"]["market_shortlist"] is False


def test_daily_slate_generates_model_only_predictions_without_odds(monkeypatch):
    frame = FootballFixtureSource.normalize_csv(_fixture_csv())

    class FakeSnapshot:
        fixtures = frame
        source = "https://www.football-data.co.uk/fixtures.csv"
        fetched_at = datetime.now(timezone.utc).isoformat()
        from_cache = True
        sha256 = "a" * 64

    class FakeSource:
        def fetch(self, **kwargs):
            return FakeSnapshot()

    monkeypatch.setattr(webapp, "fixture_source", lambda: FakeSource())
    response = client.get("/api/daily/slate?date=2026-08-03&horizon_days=2&refresh=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["credits_consumed"] == 0
    assert body["summary"]["model_predictions"] >= 1
    event = body["events"][0]
    assert event["decision"] == "probabilités seulement"
    assert event["winamax_odds"] is False
    assert abs(sum(event["probabilities"].values()) - 1.0) < 1e-8
    assert body["upcoming_events"]


def test_daily_slate_keeps_promoted_club_fixture_as_cold_start(monkeypatch):
    frame = FootballFixtureSource.normalize_csv(
        (
            "Div,Date,Time,HomeTeam,AwayTeam\n"
            "E0,21/08/2026,20:00,Arsenal,Coventry City\n"
        ).encode("utf-8")
    )

    class FakeSnapshot:
        fixtures = frame
        source = "fixture-test"
        fetched_at = datetime.now(timezone.utc).isoformat()
        from_cache = True
        sha256 = "b" * 64

    class FakeSource:
        def fetch(self, **kwargs):
            return FakeSnapshot()

    monkeypatch.setattr(webapp, "fixture_source", lambda: FakeSource())
    response = client.get("/api/daily/slate?date=2026-08-21&horizon_days=0&refresh=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["model_predictions"] == 1
    assert body["summary"]["cold_start_predictions"] == 1
    event = body["events"][0]
    assert event["coverage_mode"] == "cold_start_league_priors"
    assert event["cold_start_model_weight"] == 0.5
    assert event["market_eligible"] is False
    assert event["probability_diagnostics"]["valid"] is True


def test_offseason_request_reports_upcoming_calendar_as_available(monkeypatch):
    frame = FootballFixtureSource.normalize_csv(
        (
            "Div,Date,Time,HomeTeam,AwayTeam\n"
            "E0,21/08/2026,20:00,Arsenal,Coventry City\n"
        ).encode("utf-8")
    )

    class FakeSnapshot:
        fixtures = frame
        source = "fixture-test"
        fetched_at = datetime.now(timezone.utc).isoformat()
        from_cache = True
        sha256 = "c" * 64

    class FakeSource:
        def fetch(self, **kwargs):
            return FakeSnapshot()

    monkeypatch.setattr(webapp, "fixture_source", lambda: FakeSource())
    response = client.get("/api/daily/slate?date=2026-08-04&horizon_days=31&refresh=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["fixtures_today"] == 0
    assert body["summary"]["upcoming_predictions"] >= 1
    assert body["fixture_status"] == "available"
    assert body["source"] == "postgresql"


def test_credit_firewall_endpoint_defaults_to_no_paid_calls():
    response = client.get("/api/credit-firewall")
    assert response.status_code == 200
    body = response.json()
    assert body["model_only_predictions_cost_credits"] == 0
    assert body["daily_odds_enabled"] is False
    assert body["automatic_bet_placement"] is False


def test_daily_product_defaults_cover_the_offseason_gap():
    assert webapp.SETTINGS.daily_fixture_horizon_days == 31
    root = Path(__file__).resolve().parents[1]
    assert "--horizon-days 31" in (root / "railway.cron.toml").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/refresh-daily-product.yml").read_text(encoding="utf-8")
    assert "default: 31" in workflow
    assert "refresh=true" in workflow


def test_daily_slate_reuses_recent_empty_refresh_without_network(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(webapp, "predictions_for_date", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        webapp,
        "recent_sync_runs",
        lambda *_args, **_kwargs: [{
            "job_name": "daily_model_only",
            "sport_key": "soccer_epl:2026-08-03",
            "status": "ok",
            "started_at": now,
            "fetched_events": 0,
        }],
    )

    def should_not_refresh(*_args, **_kwargs):
        raise AssertionError("recent empty refresh should suppress another provider request")

    monkeypatch.setattr(webapp, "_generate_daily_model_predictions", should_not_refresh)
    payload = webapp._daily_slate_payload("2026-08-03", horizon_days=31)
    assert payload["generation"]["status"] == "recent_empty_refresh"
    assert payload["summary"]["credits_consumed"] == 0


def test_frontend_does_not_probe_paid_sports_when_firewall_is_closed():
    script = (Path(__file__).resolve().parents[1] / "static/app.js").read_text(encoding="utf-8")
    assert "loaded.provider?.configured&&loaded.provider?.paid_calls_enabled" in script
    assert "$('#loadLiveOdds').disabled=!paidOddsAvailable" in script


def test_daily_renderer_executes_model_only_payload() -> None:
    import subprocess

    script = r"""
const fs = require('fs');
const vm = require('vm');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) {
    elements.set(selector, {
      textContent: '', innerHTML: '', value: '', hidden: false, disabled: false,
      className: '', options: [],
      classList: {add(){}, remove(){}, toggle(){}, contains(){return false;}},
      addEventListener(){}, removeEventListener(){}, focus(){},
    });
  }
  return elements.get(selector);
}
const context = {
  console,
  document: {querySelector: element},
  window: {location: {assign(){}}},
  setTimeout(){},
  Headers,
  fetch: async () => ({ok: true, status: 200, json: async () => ({})}),
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/app.js', 'utf8').replace(/\ninit\(\);\s*\n/, '\n'), context);
vm.runInContext(`renderDaily({
  summary: {fixtures_today: 1, model_predictions: 1, research_candidates: 0, upcoming_predictions: 1, credits_consumed: 0},
  credit_firewall: {daily_odds_enabled: false, daily_odds_max_credits: 0},
  no_shortlist_reasons: ['cotes payantes désactivées'],
  model_diagnostics: {status: 'operational_research', model_version: '4.5.0', metrics: {n_test: 380, log_loss: 1.06}, freshness: {age_days: 70}},
  events: [{sport: 'football', competition: 'E0', event: 'Arsenal — Chelsea', date: '2026-08-03', decision: 'probabilités seulement', model_version: '4.5.0', probabilities: {home: 0.47, draw: 0.27, away: 0.26}, probability_diagnostics: {valid: true}, reasons: ['cotes non demandées'], winamax_odds: false}],
  upcoming_events: [{sport: 'football', competition: 'E0', event: 'Liverpool — Man City', date: '2026-08-05', decision: 'probabilités seulement', model_version: '4.5.0', probabilities: {home: 0.40, draw: 0.28, away: 0.32}, probability_diagnostics: {valid: true}, reasons: [], winamax_odds: false}]
})`, context);
if (elements.get('#dailyPredictionCount').textContent !== 1) process.exit(2);
if (!elements.get('#dailySlate').innerHTML.includes('47.0 %')) process.exit(3);
if (!elements.get('#upcomingSlate').innerHTML.includes('Liverpool')) process.exit(4);
if (elements.get('#dailyCredits').textContent !== 0) process.exit(5);
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
