from __future__ import annotations

from pathlib import Path
import subprocess

import pandas as pd
from fastapi.testclient import TestClient

import webapp
from sports_predictor.challenger_factory import (
    ChallengerFactoryLimits,
    build_challenger_factory_report,
    dataset_snapshot,
    train_tennis_challenger,
)

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(webapp.app)


def _tennis_history(rows: int = 180) -> pd.DataFrame:
    players = [f"Player {index}" for index in range(16)]
    surfaces = ["hard", "clay", "grass"]
    output = []
    for index in range(rows):
        day = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=index // 3)
        first = players[index % len(players)]
        second = players[(index * 5 + 3) % len(players)]
        if first == second:
            second = players[(index + 1) % len(players)]
        winner, loser = (first, second) if index % 4 else (second, first)
        output.append({
            "date": day.isoformat(),
            "tour": "ATP" if index % 2 else "WTA",
            "surface": surfaces[index % len(surfaces)],
            "tournament_level": "A",
            "tournament": f"Tournament {index // 12}",
            "best_of": 3,
            "winner_name": winner,
            "loser_name": loser,
            "winner_rank": 1 + index % 80,
            "loser_rank": 1 + (index * 3) % 100,
            "winner_rank_points": 6000 - index % 3000,
            "loser_rank_points": 5000 - (index * 2) % 3000,
        })
    return pd.DataFrame(output)


def test_dataset_snapshot_is_stable_and_hashes_content():
    frame = _tennis_history(24)
    first = dataset_snapshot(frame, sport="tennis", source="test")
    second = dataset_snapshot(frame.sample(frac=1, random_state=7), sport="tennis", source="test")
    assert first["dataset_sha256"] == second["dataset_sha256"]
    changed = frame.copy()
    changed.loc[0, "winner_rank"] = 999
    assert dataset_snapshot(changed, sport="tennis", source="test")["dataset_sha256"] != first["dataset_sha256"]


def test_surface_aware_tennis_challenger_trains_without_provider():
    report = train_tennis_challenger(
        _tennis_history(),
        limits=ChallengerFactoryLimits(minimum_rows=120, minimum_distinct_dates=12),
    )
    assert report["status"] in {"candidate", "hold"}
    assert report["model_type"] == "surface_aware_regularized_logistic"
    assert set(report["surface_holdout"]) == {"clay", "grass", "hard"}
    assert report["provider_credits_consumed"] == 0
    assert report["automatic_promotion"] is False


def test_local_factory_builds_real_football_challenger_and_refuses_tiny_tennis():
    report = build_challenger_factory_report(root=ROOT)
    assert report["sports"]["football"]["status"] in {"candidate", "hold"}
    assert report["sports"]["football"]["dataset"]["rows"] >= 1000
    assert report["sports"]["tennis"]["status"] == "collecting"
    assert report["limits"]["provider_credits_consumed"] == 0


def test_challenger_factory_get_is_read_only(monkeypatch):
    monkeypatch.setattr(webapp, "_challenger_factory_artifact", lambda: {
        "status": "collecting", "sports": {},
        "limits": {"provider_credits_consumed": 0, "automatic_promotion": False},
    })
    response = client.get("/api/challenger-factory")
    assert response.status_code == 200
    assert response.json()["limits"]["provider_credits_consumed"] == 0


def test_challenger_factory_run_requires_exact_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "build_challenger_factory_report", lambda **kwargs: {
        "status": "collecting", "sports": {"football": {"status": "hold"}, "tennis": {"status": "collecting"}},
        "limits": {"maximum_models_per_sport": 4, "provider_credits_consumed": 0, "automatic_promotion": False},
    })
    monkeypatch.setattr(webapp, "record_benchmark_run", lambda **kwargs: 470)
    denied = client.post("/api/challenger-factory/run", json={"confirmation": "NO"})
    assert denied.status_code == 409
    accepted = client.post("/api/challenger-factory/run", json={"confirmation": "RUN_CHALLENGER_FACTORY"})
    assert accepted.status_code == 200
    assert accepted.json()["run"]["id"] == 470


def test_simple_ui_is_capped_and_exposes_session_health():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="sessionStatus"' in html
    assert 'id="learningFootballState"' in html
    assert 'id="learningTennisState"' in html
    assert 'app.js?v=4.9.0' in html
    assert "MAX_VISIBLE_CARDS = 8" in js
    assert "INFLIGHT_GETS" in js
    assert "REQUEST_TIMEOUT_MS" in js
    assert ".learning-compact-grid" in css


def test_frontend_deduplicates_gets_and_caps_cards_in_node():
    script = r'''
const fs=require('fs'); const vm=require('vm'); const elements=new Map(); let calls=0;
function element(selector){if(!elements.has(selector)) elements.set(selector,{textContent:'',innerHTML:'',hidden:false,disabled:false,style:{},className:'',dataset:{},classList:{add(){},remove(){},toggle(){},contains(){return false;}},setAttribute(){},addEventListener(){},scrollIntoView(){}}); return elements.get(selector);}
const context={console,AbortController,clearTimeout,document:{querySelector:element,querySelectorAll(){return []},body:element('body')},window:{location:{assign(){}},addEventListener(){}},localStorage:{getItem(){return null},setItem(){}},setTimeout,clearTimeout,Headers,fetch:async()=>{calls++; await new Promise(r=>setTimeout(r,5)); return {ok:true,status:200,json:async()=>({ok:true})};}};
vm.createContext(context); const source=fs.readFileSync('static/app.js','utf8').replace(/\ninit\(\);\s*\n/,'\n'); vm.runInContext(source,context);
(async()=>{
 await Promise.all([context.jsonFetch('/same'),context.jsonFetch('/same')]);
 if(calls!==1) process.exit(2);
 const events=Array.from({length:12},(_,i)=>({sport:'football',competition:'E0',event:`A${i} — B${i}`,date:'2026-08-20',decision:'probabilités seulement',model_version:'4.9.0',probabilities:{home:.4,draw:.3,away:.3},probability_diagnostics:{valid:true},reasons:[],winamax_odds:false}));
 context.renderDaily({summary:{model_predictions:12,fixtures_today:12,upcoming_predictions:0,cold_start_predictions:0,research_candidates:0,credits_consumed:0},events,upcoming_events:[],credit_firewall:{daily_odds_enabled:false},no_shortlist_reasons:[]});
 const count=(elements.get('#dailySlate').innerHTML.match(/slate-card/g)||[]).length;
 if(count!==8) process.exit(3);
 if(elements.get('#dailyOverflow').hidden!==false) process.exit(4);
})().catch(()=>process.exit(5));
'''
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


def test_challenger_workflow_is_zero_credit_and_bounded():
    workflow = (ROOT / ".github" / "workflows" / "run-challenger-factory.yml").read_text(encoding="utf-8")
    assert "scripts.run_challenger_factory" in workflow
    assert "provider_credits_consumed" in workflow
    assert "THE_ODDS_API_KEY" not in workflow
    assert "timeout-minutes: 25" in workflow
