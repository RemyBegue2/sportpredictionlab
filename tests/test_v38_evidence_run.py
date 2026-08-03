from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from sports_predictor.evidence_quality import build_evidence_quality_report, canonical_event_id, temporal_row_audit
from sports_predictor.sample_plan import build_sample_request_plan, validate_plan_request_id


def _events() -> pd.DataFrame:
    return pd.DataFrame([
        {"sport_key": "soccer_epl", "event_id": "e1", "commence_time": "2026-08-10T19:00:00Z", "home_team": "Arsenal", "away_team": "Chelsea"},
        {"sport_key": "soccer_epl", "event_id": "e2", "commence_time": "2026-08-11T19:00:00Z", "home_team": "Liverpool", "away_team": "Everton"},
    ])


def _odds() -> pd.DataFrame:
    rows = []
    for event in _events().to_dict(orient="records"):
        for bookmaker in ("winamax_fr", "pinnacle"):
            for outcome, price in (("Home", 2.1), ("Draw", 3.4), ("Away", 3.2)):
                rows.append({
                    **event,
                    "bookmaker_key": bookmaker,
                    "market_key": "h2h",
                    "outcome_name": outcome,
                    "price": price,
                    "requested_snapshot_at": pd.Timestamp(event["commence_time"]) - pd.Timedelta(hours=1),
                })
    return pd.DataFrame(rows)


def test_zero_credit_request_plan_is_deterministic_and_guarded() -> None:
    kwargs = dict(
        sport_key="soccer_epl",
        start_date="2026-08-01",
        end_date="2026-08-07",
        sample_events=30,
        horizons_hours=[1],
        max_discovery_calls=14,
        max_odds_credits=120,
    )
    first = build_sample_request_plan(**kwargs)
    second = build_sample_request_plan(**kwargs)
    assert first.plan_request_id == second.plan_request_id
    assert first.plan_request_id.startswith("REQ-")
    assert first.consumes_credits is False
    assert first.estimated_discovery_calls == 7
    validate_plan_request_id(first, first.plan_request_id)


def test_request_plan_rejects_unsafe_caps_and_missing_winamax() -> None:
    try:
        build_sample_request_plan(
            sport_key="soccer_epl", start_date="2026-08-01", end_date="2026-08-02",
            sample_events=31, max_discovery_calls=14, max_odds_credits=120,
        )
    except ValueError as exc:
        assert "sample_events" in str(exc)
    else:
        raise AssertionError("unsafe event cap accepted")
    try:
        build_sample_request_plan(
            sport_key="soccer_epl", start_date="2026-08-01", end_date="2026-08-02",
            bookmakers=["pinnacle"], max_discovery_calls=14, max_odds_credits=120,
        )
    except ValueError as exc:
        assert "winamax_fr" in str(exc)
    else:
        raise AssertionError("sample without Winamax accepted")


def test_temporal_audit_quarantines_odds_at_or_after_kickoff() -> None:
    frame = _odds().head(2).copy()
    frame.loc[frame.index[1], "requested_snapshot_at"] = frame.loc[frame.index[1], "commence_time"]
    clean, issues = temporal_row_audit(frame)
    assert len(clean) == 1
    assert len(issues) == 1
    assert "odds_not_strictly_before_event" in issues.iloc[0]["issues"]


def test_quality_report_passes_clean_technical_sample_without_profit_claim() -> None:
    report = build_evidence_quality_report(
        plan={"plan_id": "p1", "plan_request_id": "REQ-1", "max_credits": 120},
        state={"status": "completed", "consumed_credits": 12},
        odds_rows=_odds(),
        events=_events(),
    )
    assert report["quality_gate"]["accepted"] is True
    assert report["quality_gate"]["status"] == "technical_validation"
    assert report["rates"]["event_coverage"] == 1.0
    assert report["rates"]["winamax_coverage"] == 1.0
    assert report["responsible_use"]["profitability_claim"] is False
    assert report["responsible_use"]["automatic_bet_placement"] is False


def test_quality_report_blocks_temporal_leakage() -> None:
    frame = _odds()
    frame.loc[frame.index[0], "requested_snapshot_at"] = frame.loc[frame.index[0], "commence_time"]
    report = build_evidence_quality_report(
        plan={"plan_id": "p1", "max_credits": 120},
        state={"status": "completed", "consumed_credits": 12},
        odds_rows=frame,
        events=_events(),
    )
    assert report["quality_gate"]["accepted"] is False
    assert "temporal_violations_detected" in report["blockers"]


def test_canonical_event_identity_is_stable() -> None:
    row = _events().iloc[0].to_dict()
    assert canonical_event_id(row) == canonical_event_id(dict(row))


def test_evidence_endpoint_and_frontend_contract(tmp_path: Path, monkeypatch) -> None:
    import webapp

    artifact = webapp.ROOT / "artifacts" / "evidence_report_v3_8.json"
    original = artifact.read_bytes() if artifact.exists() else None
    payload = {
        "app_version": "3.8.0",
        "quality_gate": {"status": "technical_validation", "accepted": True, "reason": "pipeline validated"},
        "counts": {"planned_events": 2, "events_with_odds": 2, "accepted_rows": 12},
        "rates": {"event_coverage": 1.0, "winamax_coverage": 1.0},
        "consumed_credits": 12,
        "blockers": [], "warnings": [],
    }
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    try:
        with TestClient(webapp.app) as client:
            response = client.get("/api/evidence")
        assert response.status_code == 200
        assert response.json()["report"]["quality_gate"]["accepted"] is True
    finally:
        if original is None:
            artifact.unlink(missing_ok=True)
        else:
            artifact.write_bytes(original)

    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "app.js").read_text(encoding="utf-8")
    for element_id in ("evidenceGate", "evidenceCoverage", "evidenceWinamax", "evidenceCredits", "evidenceIssues", "refreshEvidence"):
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js
    assert "jsonFetch('/api/evidence')" in js


def test_v38_workflows_are_browser_operated_and_capped() -> None:
    root = Path(__file__).resolve().parents[1]
    workflows = root / ".github" / "workflows"
    estimate = (workflows / "estimate-historical-sample.yml").read_text(encoding="utf-8")
    run = (workflows / "run-historical-sample.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in estimate
    assert "Provider API calls executed: **0**" in estimate
    assert "EXECUTE_APPROVED_SAMPLE" in run
    assert "scripts.build_evidence_report" in run
    assert "Enforce quality gate after publishing the diagnostic" in run
    assert "max_odds_credits" in run
    assert "railway up" in run
