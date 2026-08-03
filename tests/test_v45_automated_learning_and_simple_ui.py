from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
import yaml

import webapp
from sports_predictor import database as database_module
from sports_predictor.roi_lab import (
    SignalPolicy,
    build_champion_challenger_report,
    simulate_bankroll_path,
    ResearchOpportunity,
)


client = TestClient(webapp.app)
ROOT = Path(__file__).resolve().parents[1]


def _candidate_roi(*, events: int = 140, football: int = 70, tennis: int = 70) -> dict:
    return {
        "generated_at": "2026-08-03T20:00:00+00:00",
        "unique_events": events,
        "optimisation": {
            "status": "candidate",
            "settled_events": events,
            "policy": SignalPolicy().to_dict(),
            "development_dates": ["2026-01-01", "2026-04-30"],
            "holdout_dates": ["2026-05-01", "2026-06-30"],
            "holdout": {"bets": 24, "roi_on_turnover": 0.06, "maximum_drawdown": 0.11},
            "cross_validation": {
                "folds": [
                    {"roi_on_turnover": 0.03},
                    {"roi_on_turnover": 0.01},
                    {"roi_on_turnover": -0.01},
                    {"roi_on_turnover": 0.02},
                ]
            },
        },
        "meta_model": {
            "status": "candidate",
            "sport_event_counts": {"football": football, "tennis": tennis},
            "holdout_dates": ["2026-05-01", "2026-06-30"],
            "portable_parameters": {
                "scaler_mean": [0, 0, 0, 0, 0, 0],
                "scaler_scale": [1, 1, 1, 1, 1, 1],
                "coef": [0, 0, 0, 0, 0, 0],
                "intercept": 0.0,
            },
        },
    }


def test_challenger_requires_manual_review_after_all_gates_pass():
    report = build_champion_challenger_report(_candidate_roi())
    assert report["status"] == "review_required"
    assert report["promotion_allowed"] is True
    assert report["automatic_promotion"] is False
    assert report["candidate_id"].startswith("RCH-")
    assert report["candidate_id"] == build_champion_challenger_report(_candidate_roi())["candidate_id"]



def test_current_champion_is_not_offered_for_duplicate_promotion():
    base = build_champion_challenger_report(_candidate_roi())
    champion = {
        "champion": base["candidate_id"],
        "status": "approved",
        "created_at": "2026-08-03T22:00:00+00:00",
        "decision": {"candidate": base["candidate"]},
    }
    report = build_champion_challenger_report(_candidate_roi(), champion=champion)
    assert report["status"] == "hold"
    assert report["promotion_allowed"] is False
    assert report["gates"]["new_challenger"]["passed"] is False

def test_challenger_collects_until_each_sport_has_enough_evidence():
    report = build_champion_challenger_report(_candidate_roi(events=90, football=70, tennis=20))
    assert report["status"] == "collecting"
    assert report["promotion_allowed"] is False
    assert report["gates"]["tennis_sample"]["passed"] is False


def test_paper_bankroll_path_is_auditable_and_never_a_real_stake():
    opportunities = [
        ResearchOpportunity(
            event_id="a", sport="football", commence_time="2026-01-01T15:00:00Z",
            selection="Home", decimal_odds=2.0, model_probability=0.65,
            edge=0.15, robust_expected_return=0.2, won=True,
        ),
        ResearchOpportunity(
            event_id="b", sport="tennis", commence_time="2026-01-02T15:00:00Z",
            selection="Player", decimal_odds=1.9, model_probability=0.62,
            edge=0.09, robust_expected_return=0.1, won=False,
        ),
    ]
    path = simulate_bankroll_path(opportunities, policy=SignalPolicy(), starting_bankroll=1000, strategy="flat_1pct")
    assert len(path) == 2
    assert path[0]["bankroll_before"] == 1000
    assert path[0]["bankroll_after"] == 1010
    assert path[1]["bankroll_after"] < path[1]["bankroll_before"]
    assert all("simulated_stake" in row for row in path)


def test_simple_interface_is_default_and_expert_data_is_lazy():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    assert '<body class="simple-mode">' in html
    assert 'id="interfaceMode"' in html
    assert 'id="learning"' in html
    assert 'data-view="expert"' in html
    assert 'app.js?v=4.5.0' in html
    assert "jsonFetch('/api/daily/slate')" in js
    assert "async function loadExpertData" in js
    assert "if(currentInterfaceMode()==='expert') await loadExpertData()" in js
    assert ".simple-mode [data-view=\"expert\"]" in css


def test_learning_renderer_executes_with_simple_payload():
    import subprocess

    script = r"""
const fs=require('fs'); const vm=require('vm'); const elements=new Map();
function element(selector){if(!elements.has(selector)) elements.set(selector,{textContent:'',innerHTML:'',style:{},className:'',classList:{add(){},remove(){},toggle(){},contains(){return false;}},setAttribute(){},addEventListener(){}}); return elements.get(selector);}
const context={console,document:{querySelector:element,querySelectorAll(){return []},body:element('body')},window:{location:{assign(){}}},localStorage:{getItem(){return null},setItem(){}},setTimeout(){},Headers,fetch:async()=>({ok:true,status:200,json:async()=>({})})};
vm.createContext(context); vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/\ninit\(\);\s*\n/,'\n'),context);
vm.runInContext(`renderLearning({status:'collecting',next_action:'Continuer',candidate:{settled_events:40,sport_event_counts:{football:25,tennis:15},candidate_id:'RCH-1234567890ABCDEF1234',holdout_bets:6},champion:{id:null},gates:{minimum_total_events:{passed:false,actual:40,required:100}}},{enabled:true,credits_consumed:1,daily_credit_cap:3,credits_remaining:2,due_events:0})`,context);
if(elements.get('#learningEvents').textContent!==40) process.exit(2);
if(!elements.get('#learningAction').innerHTML.includes('Continuer la collecte')) process.exit(3);
if(elements.get('#learningBudget').textContent!=='1 / 3') process.exit(4);
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


def test_automated_capture_skips_paid_football_on_empty_free_day(monkeypatch):
    monkeypatch.setattr(
        webapp,
        "SETTINGS",
        replace(
            webapp.SETTINGS,
            automated_shadow_enabled=True,
            daily_odds_enabled=True,
            daily_odds_max_credits=3,
            daily_tennis_max_tournaments=0,
            shadow_enabled=True,
        ),
    )
    monkeypatch.setattr(webapp, "research_credits_consumed_on", lambda date: {"date": date, "credits_consumed": 0, "runs": []})
    monkeypatch.setattr(webapp, "_daily_slate_payload", lambda *args, **kwargs: {"summary": {"fixtures_today": 0}})
    monkeypatch.setattr(webapp, "_football_odds_slate", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("paid call must not run")))
    monkeypatch.setattr(webapp, "settle_shadow_predictions", lambda: {"settled": 0, "skipped": 0})
    monkeypatch.setattr(webapp, "recent_shadow_predictions", lambda *args, **kwargs: [])
    monkeypatch.setattr(webapp, "latest_model_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(webapp, "due_shadow_events", lambda limit=500: [])
    monkeypatch.setattr(webapp, "record_benchmark_run", lambda **kwargs: 451)
    response = client.post("/api/research-lab/refresh", json={
        "date": "2026-08-03", "max_credits": 3, "tennis_limit": 0,
        "tennis_sport_keys": [], "automation": True, "confirmation": "CAPTURE_DAILY_MARKET",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["credits_consumed"] == 0
    assert body["credit_budget"]["remaining_after"] == 3
    assert body["run"]["id"] == 451


def test_shared_daily_budget_blocks_another_paid_capture(monkeypatch):
    monkeypatch.setattr(
        webapp,
        "SETTINGS",
        replace(webapp.SETTINGS, automated_shadow_enabled=True, daily_odds_enabled=True, daily_odds_max_credits=3, shadow_enabled=True),
    )
    monkeypatch.setattr(webapp, "research_credits_consumed_on", lambda date: {"date": date, "credits_consumed": 3, "runs": [{"id": 1}]})
    response = client.post("/api/research-lab/refresh", json={
        "date": "2026-08-03", "max_credits": 3, "tennis_limit": 0,
        "tennis_sport_keys": [], "automation": True, "confirmation": "CAPTURE_DAILY_MARKET",
    })
    assert response.status_code == 409
    assert "budget is exhausted" in response.text


def test_settlement_is_zero_credit_noop_when_nothing_is_due(monkeypatch):
    monkeypatch.setattr(
        webapp,
        "SETTINGS",
        replace(webapp.SETTINGS, automated_shadow_enabled=True, daily_odds_enabled=True, daily_odds_max_credits=3),
    )
    monkeypatch.setattr(webapp, "research_credits_consumed_on", lambda date: {"date": date, "credits_consumed": 3, "runs": []})
    monkeypatch.setattr(webapp, "due_shadow_events", lambda limit=500: [])
    monkeypatch.setattr(webapp, "settle_shadow_predictions", lambda: {"settled": 0, "skipped": 0})
    monkeypatch.setattr(webapp, "recent_shadow_predictions", lambda *args, **kwargs: [])
    monkeypatch.setattr(webapp, "latest_model_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(webapp, "latest_benchmark_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(webapp, "record_benchmark_run", lambda **kwargs: 452)
    response = client.post("/api/research-lab/settle", json={
        "max_credits": 3, "automation": True, "confirmation": "SETTLE_DAILY_MARKET",
    })
    assert response.status_code == 200, response.text
    assert response.json()["settlement"]["credits_consumed"] == 0
    assert response.json()["run"]["id"] == 452


def test_automated_request_is_blocked_when_feature_flag_is_off(monkeypatch):
    monkeypatch.setattr(
        webapp,
        "SETTINGS",
        replace(webapp.SETTINGS, automated_shadow_enabled=False, daily_odds_enabled=True, daily_odds_max_credits=3, shadow_enabled=True),
    )
    response = client.post("/api/research-lab/refresh", json={
        "max_credits": 1, "tennis_limit": 0, "tennis_sport_keys": [],
        "automation": True, "confirmation": "CAPTURE_DAILY_MARKET",
    })
    assert response.status_code == 409
    assert "AUTOMATED_SHADOW_ENABLED" in response.text


def test_champion_promotion_requires_all_current_gates(monkeypatch):
    monkeypatch.setattr(webapp, "_latest_research_payload", lambda: {
        "learning": {"candidate_id": "RCH-1234567890ABCDEF1234", "promotion_allowed": False},
        "roi_lab": {}, "run": {"id": 1},
    })
    response = client.post("/api/research-lab/champion/promote", json={
        "candidate_id": "RCH-1234567890ABCDEF1234",
        "confirmation": "PROMOTE_RESEARCH_CHAMPION",
        "note": "reviewed",
    })
    assert response.status_code == 409
    assert "has not passed" in response.text


def test_manual_champion_promotion_records_no_automatic_action(monkeypatch):
    learning = build_champion_challenger_report(_candidate_roi())
    monkeypatch.setattr(webapp, "_latest_research_payload", lambda: {
        "learning": learning, "roi_lab": _candidate_roi(), "run": {"id": 45},
    })
    recorded = {}
    monkeypatch.setattr(webapp, "record_model_decision", lambda **kwargs: recorded.update(kwargs) or 99)
    response = client.post("/api/research-lab/champion/promote", json={
        "candidate_id": learning["candidate_id"],
        "confirmation": "PROMOTE_RESEARCH_CHAMPION",
        "note": "validated after human review",
    })
    assert response.status_code == 200, response.text
    assert response.json()["automatic_promotion"] is False
    assert recorded["decision"]["automatic_bet_placement"] is False



def test_shared_credit_ledger_sums_only_paid_research_modes(monkeypatch):
    class Row:
        def __init__(self, row_id, mode, credits):
            self.id = row_id
            self.config = {"mode": mode}
            self.summary = {"credits_consumed": credits}
            self.started_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)

    class ScalarResult:
        def all(self):
            return [
                Row(1, "daily_live_market_shadow", 2),
                Row(2, "daily_result_settlement", 1),
                Row(3, "roi_policy_optimisation", 99),
            ]

    class Session:
        def scalars(self, statement):
            return ScalarResult()

    @contextmanager
    def fake_session_scope():
        yield Session()

    monkeypatch.setattr(database_module, "session_scope", fake_session_scope)
    result = database_module.research_credits_consumed_on("2026-08-03")
    assert result["credits_consumed"] == 3
    assert [row["id"] for row in result["runs"]] == [1, 2]


def test_shared_credit_ledger_rejects_invalid_date():
    try:
        database_module.research_credits_consumed_on("03/08/2026")
    except ValueError as exc:
        assert "YYYY-MM-DD" in str(exc)
    else:
        raise AssertionError("invalid date should be rejected")

def test_v45_workflows_are_bounded_and_promotion_is_manual():
    automated_path = ROOT / ".github" / "workflows" / "automated-shadow-learning.yml"
    promotion_path = ROOT / ".github" / "workflows" / "promote-research-champion.yml"
    automated = automated_path.read_text(encoding="utf-8")
    promotion = promotion_path.read_text(encoding="utf-8")
    yaml.safe_load(automated)
    yaml.safe_load(promotion)
    assert "AUTOMATED_SHADOW_MAX_CREDITS" in automated
    assert "automation': True" in automated
    assert "api/research-lab/optimise" in automated
    assert "automatic promotion invariant" in automated
    assert "PROMOTE_RESEARCH_CHAMPION" in promotion
    assert "workflow_dispatch" in promotion
    assert "schedule:" not in promotion


def test_browser_smoke_covers_simple_then_expert_mode():
    source = (ROOT / "scripts" / "browser_smoke_test.py").read_text(encoding="utf-8")
    assert "simple mode is not the default" in source
    assert "deferred expert view did not render" in source
    assert "#learningChallenger" in source
    assert "page.click(\"#interfaceMode\")" in source
