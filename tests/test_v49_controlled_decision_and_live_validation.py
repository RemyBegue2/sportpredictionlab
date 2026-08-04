from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
from fastapi.testclient import TestClient

import webapp
from sports_predictor.controlled_decision import (
    build_bounded_football_round,
    build_controlled_model_decision_report,
    build_incremental_tennis_package,
)

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(webapp.app)


def tennis_rows(start: int, count: int, *, dates: int = 8) -> pd.DataFrame:
    rows = []
    for index in range(start, start + count):
        date = pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=index % dates)
        rows.append({
            "date": date.isoformat(),
            "tour": "ATP",
            "surface": "Hard" if index % 2 == 0 else "Clay",
            "tournament": f"T{index // 4}",
            "tournament_level": "A",
            "best_of": 3,
            "winner_name": f"Player {index % 11}",
            "loser_name": f"Player {(index + 5) % 11}",
            "winner_rank": index + 1,
            "loser_rank": index + 20,
            "winner_rank_available_at": (date - pd.Timedelta(days=1)).isoformat(),
            "loser_rank_available_at": (date - pd.Timedelta(days=1)).isoformat(),
        })
    return pd.DataFrame(rows)


def test_bounded_football_round_trains_only_two_and_requires_future_holdout():
    frame = pd.read_csv(ROOT / "data" / "real" / "football_epl_2021_2026.csv")
    report = build_bounded_football_round(frame)
    assert len(report["challengers"]) == 2
    assert {row["model_type"] for row in report["challengers"]} == {
        "regularized_poisson_attack_defence",
        "hybrid_poisson_elo",
    }
    assert report["promotion_ready"] is False
    assert report["promotion_holdout_generation"]["status"] == "open_collecting"
    assert report["consulted_holdout_generation"]["consulted"] is True
    assert report["provider_credits_consumed"] == 0
    assert all(row["artifact_sha256"] for row in report["challengers"])


def test_incremental_tennis_import_deduplicates_and_versions_correction():
    previous = tennis_rows(0, 12)
    incoming = tennis_rows(12, 4)
    unchanged = previous.iloc[[0]].copy()
    correction = previous.iloc[[1]].copy()
    correction[["winner_name", "loser_name"]] = correction[["loser_name", "winner_name"]].to_numpy()
    incoming = pd.concat([incoming, unchanged, correction], ignore_index=True)
    package = build_incremental_tennis_package(
        previous,
        incoming,
        source="test_incremental",
        license_status="approved",
        previous_dataset_id="DS-TENNIS-OLD",
    )
    assert package["catalog"]["supersedes_dataset_id"] == "DS-TENNIS-OLD"
    assert package["incremental"]["unchanged_duplicates"] == 1
    assert package["incremental"]["result_corrections"] == 1
    assert package["incremental"]["merged_rows"] == 16
    assert package["incremental"]["provider_credits_consumed"] == 0


def test_controlled_decision_requires_public_simple_and_expert_proof(tmp_path):
    root = tmp_path
    (root / "artifacts").mkdir()
    (root / "data" / "real").mkdir(parents=True)
    (root / "data" / "real_snapshot").mkdir(parents=True)
    (ROOT / "data" / "real" / "football_epl_2021_2026.csv").replace if False else None
    # Use explicit source paths so only the production reports live in the temporary root.
    simple = {"status": "ok", "expected_version": "4.9.0", "console_errors": [], "page_errors": [], "one_compact_panel_at_a_time": True, "dom_growth": 1}
    (root / "artifacts" / "public_long_session_v4_9_simple.json").write_text(json.dumps(simple), encoding="utf-8")
    report = build_controlled_model_decision_report(
        root=root,
        football_path=ROOT / "data" / "real" / "football_epl_2021_2026.csv",
        tennis_path=ROOT / "data" / "real_snapshot" / "tennis_atp_2025_snapshot.csv",
    )
    assert report["production_validation"]["status"] == "not_proven"
    expert = {**simple}
    (root / "artifacts" / "public_long_session_v4_9_expert.json").write_text(json.dumps(expert), encoding="utf-8")
    report = build_controlled_model_decision_report(
        root=root,
        football_path=ROOT / "data" / "real" / "football_epl_2021_2026.csv",
        tennis_path=ROOT / "data" / "real_snapshot" / "tennis_atp_2025_snapshot.csv",
    )
    assert report["production_validation"]["status"] == "passed"
    assert report["limits"]["provider_credits_consumed"] == 0
    assert report["limits"]["automatic_promotion"] is False


def test_controlled_decision_api_read_and_exact_confirmation(monkeypatch):
    sample = {
        "status": "hold",
        "football": {"status": "hold", "challengers": [], "promotion_ready": False},
        "tennis": {"training_status": "blocked_below_readiness_gates", "progress": {}},
        "production_validation": {"status": "not_proven"},
        "limits": {"provider_credits_consumed": 0, "automatic_promotion": False},
    }
    monkeypatch.setattr(webapp, "_controlled_model_decision_artifact", lambda: sample)
    assert client.get("/api/controlled-model-decision").json() == sample
    denied = client.post("/api/controlled-model-decision/run", json={"confirmation": "NO"})
    assert denied.status_code == 409


def test_v49_ui_and_workflows_remain_compact_and_zero_credit():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert html.count('class="simple-tab') == 3
    assert 'id="controlledDecisionDetails"' in html
    assert "app.js?v=4.9.0" in html
    assert "renderControlledDecision" in js
    assert "/api/controlled-model-decision" in js
    workflow = (ROOT / ".github" / "workflows" / "run-controlled-model-decision.yml").read_text(encoding="utf-8")
    assert "THE_ODDS_API_KEY" not in workflow
    assert "maximum_football_challengers" in workflow
    long_session = (ROOT / ".github" / "workflows" / "verify-long-session.yml").read_text(encoding="utf-8")
    assert "scenario: [simple, expert]" in long_session
    assert "--long-session-scenario" in long_session
