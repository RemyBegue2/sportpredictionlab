from __future__ import annotations

from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

import webapp
from sports_predictor.feature_lab import (
    ExperimentSpec,
    build_feature_lab_report,
    calibrate_sport,
    experiment_identifier,
    validate_feature_lineage,
)


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(webapp.app)


def _football_rows(count: int = 48) -> list[dict]:
    rows = []
    outcomes = ["home", "draw", "away"]
    for index in range(count):
        outcome = outcomes[index % 3]
        base = {
            "home": {"home": 0.58, "draw": 0.24, "away": 0.18},
            "draw": {"home": 0.35, "draw": 0.38, "away": 0.27},
            "away": {"home": 0.20, "draw": 0.23, "away": 0.57},
        }[outcome]
        rows.append({
            "provider_event_id": f"football-{index}",
            "sport": "football",
            "status": "settled",
            "temporal_valid": True,
            "commence_time": f"2026-{1 + index // 24:02d}-{1 + index % 24:02d}T15:00:00Z",
            "prediction_created_at": f"2026-{1 + index // 24:02d}-{1 + index % 24:02d}T10:00:00Z",
            "probabilities": base,
            "evaluation": {"result_class": outcome},
            "fixture": {"feature_manifest": [{
                "feature_name": "elo_diff",
                "available_at": f"2026-{1 + index // 24:02d}-{1 + index % 24:02d}T09:00:00Z",
            }]},
        })
    return rows


def _tennis_rows(count: int = 48) -> list[dict]:
    rows = []
    for index in range(count):
        player_1_wins = index % 2 == 0
        rows.append({
            "provider_event_id": f"tennis-{index}",
            "sport": "tennis",
            "status": "settled",
            "temporal_valid": True,
            "commence_time": f"2026-{3 + index // 24:02d}-{1 + index % 24:02d}T15:00:00Z",
            "prediction_created_at": f"2026-{3 + index // 24:02d}-{1 + index % 24:02d}T10:00:00Z",
            "probabilities": {"player_1": 0.66 if player_1_wins else 0.34, "player_2": 0.34 if player_1_wins else 0.66},
            "evaluation": {"result_class": "player_1" if player_1_wins else "player_2"},
            "fixture": {"feature_manifest": [{
                "feature_name": "surface_elo",
                "available_at": f"2026-{3 + index // 24:02d}-{1 + index % 24:02d}T09:00:00Z",
            }]},
        })
    return rows


def test_experiment_identifier_is_reproducible_and_order_sensitive():
    first = ExperimentSpec("football", "test", ("elo", "rest"))
    second = ExperimentSpec("football", "test", ("elo", "rest"))
    third = ExperimentSpec("football", "test", ("rest", "elo"))
    assert experiment_identifier(first) == experiment_identifier(second)
    assert experiment_identifier(first).startswith("EXP-")
    assert experiment_identifier(first) != experiment_identifier(third)


def test_feature_lineage_rejects_future_information():
    result = validate_feature_lineage(
        [{"feature_name": "injury", "available_at": "2026-08-04T13:00:00Z"}],
        prediction_created_at="2026-08-04T12:00:00Z",
    )
    assert result["valid"] is False
    assert result["issues"][0]["reason"] == "future_feature"


def test_calibration_is_bounded_and_uses_untouched_holdout():
    report = calibrate_sport(_football_rows(), sport="football")
    assert report["events"] == 48
    assert report["calibration_events"] + report["holdout_events"] == 48
    assert report["selected_calibrator"] in {"identity", "temperature_multiclass"}
    assert report["provider_credits_consumed"] == 0
    assert report["holdout"]["log_loss"] >= 0


def test_tennis_calibration_and_feature_lab_are_separate_by_sport():
    rows = _football_rows() + _tennis_rows()
    report = build_feature_lab_report(rows)
    assert report["sports"]["football"]["events"] == 48
    assert report["sports"]["tennis"]["events"] == 48
    assert report["limits"]["maximum_experiments_per_sport"] == 12
    assert report["limits"]["provider_credits_consumed"] == 0
    assert report["feature_lineage"]["valid"] is True
    assert len(report["experiments"]) == 2


def test_feature_lab_collects_instead_of_inventing_confidence():
    report = build_feature_lab_report(_football_rows(12))
    assert report["status"] == "collecting"
    assert report["sports"]["football"]["reliability"] == "INSUFFICIENT_EVIDENCE"
    assert report["sports"]["tennis"]["events"] == 0


def test_feature_lab_api_never_needs_provider(monkeypatch):
    monkeypatch.setattr(webapp, "recent_shadow_predictions", lambda *args, **kwargs: _football_rows() + _tennis_rows())
    response = client.get("/api/feature-lab")
    assert response.status_code == 200
    body = response.json()
    assert body["limits"]["provider_credits_consumed"] == 0
    assert body["limits"]["automatic_promotion"] is False


def test_feature_lab_post_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(webapp, "recent_shadow_predictions", lambda *args, **kwargs: _football_rows() + _tennis_rows())
    monkeypatch.setattr(webapp, "record_benchmark_run", lambda **kwargs: 460)
    denied = client.post("/api/feature-lab/run", json={"confirmation": "NO"})
    assert denied.status_code == 409
    accepted = client.post("/api/feature-lab/run", json={"confirmation": "RUN_FEATURE_LAB"})
    assert accepted.status_code == 200
    assert accepted.json()["run"]["id"] == 460


def test_compact_interface_shows_one_primary_panel_and_lazy_expert_mode():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-simple-panel="today"' in html
    assert 'data-simple-panel="signals"' in html
    assert 'data-simple-panel="learning"' in html
    assert 'data-simple-target="today"' in html
    assert 'app.js?v=4.9.0' in html
    assert 'body.simple-mode [data-simple-panel]{display:none}' in css
    assert 'function applySimplePanel' in js
    assert "jsonFetch('/api/feature-lab')" in js


def test_feature_lab_renderer_executes_in_node():
    script = r"""
const fs=require('fs'); const vm=require('vm'); const elements=new Map();
function element(selector){if(!elements.has(selector)) elements.set(selector,{textContent:'',innerHTML:'',style:{},className:'',dataset:{},classList:{add(){},remove(){},toggle(){},contains(){return false;}},setAttribute(){},addEventListener(){},scrollIntoView(){}}); return elements.get(selector);}
const context={console,document:{querySelector:element,querySelectorAll(){return []},body:element('body')},window:{location:{assign(){}}},localStorage:{getItem(){return null},setItem(){}},setTimeout(){},Headers,fetch:async()=>({ok:true,status:200,json:async()=>({})})};
vm.createContext(context); vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/\ninit\(\);\s*\n/,'\n'),context);
vm.runInContext(`renderFeatureLab({overall_reliability:'medium',sports:{football:{status:'candidate',reliability:'MEDIUM_CONFIDENCE_RESEARCH',events:72,selected_calibrator:'temperature_multiclass',holdout:{log_loss:.91,ece:.08}},tennis:{status:'collecting',reliability:'INSUFFICIENT_EVIDENCE',events:18,selected_calibrator:'identity',reason:'insufficient'}}})`,context);
if(!elements.get('#featureReliability').innerHTML.includes('Football : moyenne')) process.exit(2);
if(!elements.get('#featureLabDetails').innerHTML.includes('Tennis')) process.exit(3);
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


def test_feature_lab_workflow_is_zero_credit_and_bounded():
    workflow = (ROOT / ".github" / "workflows" / "run-feature-lab.yml").read_text(encoding="utf-8")
    assert "scripts.run_feature_lab" in workflow
    assert "provider_credits_consumed" in workflow
    assert "THE_ODDS_API_KEY" not in workflow
    assert "timeout-minutes: 20" in workflow
