from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

import webapp
from sports_predictor.evidence_acceleration import (
    TennisReadinessLimits,
    build_evidence_acceleration_report,
    build_tennis_dataset_package,
    normalise_tennis_import,
)

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(webapp.app)


def tennis_frame(rows: int = 24, *, dates: int = 12) -> pd.DataFrame:
    output = []
    surfaces = ["Hard", "Clay", "Grass"]
    for index in range(rows):
        date = pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=index % dates)
        output.append({
            "date": date.isoformat(),
            "tour": "ATP",
            "surface": surfaces[index % 3],
            "tournament": f"T{index // 6}",
            "tournament_level": "A",
            "best_of": 3,
            "winner_name": f"Player {index % 9}",
            "loser_name": f"Player {(index + 4) % 9}",
            "winner_rank": index + 1,
            "loser_rank": index + 10,
            "winner_rank_available_at": (date - pd.Timedelta(days=1)).isoformat(),
            "loser_rank_available_at": (date - pd.Timedelta(days=1)).isoformat(),
        })
    return pd.DataFrame(output)


def test_tennis_import_quarantines_duplicates_and_future_rankings():
    frame = tennis_frame(12)
    duplicate = frame.iloc[[0]].copy()
    future = frame.iloc[[1]].copy()
    future["winner_rank_available_at"] = (pd.Timestamp(future.iloc[0]["date"]) + pd.Timedelta(days=1)).isoformat()
    accepted, quarantined, quality = normalise_tennis_import(pd.concat([frame, duplicate, future], ignore_index=True))
    assert len(accepted) == 12
    issues = {issue for row in quarantined["quality_issues"] for issue in row}
    assert "duplicate_row" in issues
    assert "future_ranking" in issues
    assert quality["duplicates"] >= 1
    assert quality["future_rankings"] == 1


def test_tennis_dataset_hash_is_stable_and_readiness_is_bounded():
    limits = TennisReadinessLimits(
        exploratory_min_rows=12,
        exploratory_min_dates=6,
        challenger_min_rows=20,
        challenger_min_dates=10,
        minimum_surface_rows_exploratory=3,
        minimum_surface_rows_challenger=5,
        minimum_distinct_surfaces=2,
    )
    frame = tennis_frame(24, dates=12)
    first = build_tennis_dataset_package(frame, source="test", license_status="approved", limits=limits)
    second = build_tennis_dataset_package(frame.sample(frac=1, random_state=4), source="test", license_status="approved", limits=limits)
    assert first["catalog"]["dataset_sha256"] == second["catalog"]["dataset_sha256"]
    assert first["catalog"]["readiness"]["challenger_ready"] is True
    changed = frame.copy()
    changed.loc[0, "winner_rank"] = 999
    third = build_tennis_dataset_package(changed, source="test", license_status="approved", limits=limits)
    assert third["catalog"]["dataset_sha256"] != first["catalog"]["dataset_sha256"]
    assert first["holdout_generation"]["generation_id"].startswith("HG-")


def test_real_evidence_report_explains_football_hold_and_refuses_tiny_tennis():
    report = build_evidence_acceleration_report(root=ROOT)
    assert report["football"]["status"] in {"hold_explained", "candidate_explained"}
    assert report["football"]["breakdowns"]["outcome"]
    assert report["football"]["bounded_next_round"]["maximum_new_challengers"] == 2
    assert report["tennis"]["catalog"]["readiness"]["status"] == "collecting"
    assert report["limits"]["provider_credits_consumed"] == 0
    assert report["limits"]["automatic_promotion"] is False


def test_evidence_api_is_read_only_and_write_requires_exact_confirmation(monkeypatch):
    sample = {
        "status": "collecting",
        "football": {"status": "hold_explained"},
        "tennis": {"catalog": {"readiness": {"status": "collecting"}}, "holdout_generation": {"status": "open_collecting"}},
        "limits": {"provider_credits_consumed": 0, "automatic_promotion": False},
    }
    monkeypatch.setattr(webapp, "_evidence_acceleration_artifact", lambda: sample)
    assert client.get("/api/evidence-acceleration").json() == sample
    response = client.post("/api/evidence-acceleration/run", json={"confirmation": "NO"})
    assert response.status_code == 409


def test_alembic_upgrade_and_downgrade(tmp_path):
    db = tmp_path / "migration.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY)"))
    env = {**__import__("os").environ, "DATABASE_URL": f"sqlite:///{db}"}
    subprocess.run(["alembic", "stamp", "20260804_0001"], cwd=ROOT, env=env, check=True, capture_output=True)
    subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True)
    tables = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert {"dataset_catalog", "holdout_generations", "alembic_version"} <= tables
    subprocess.run(["alembic", "downgrade", "20260804_0001"], cwd=ROOT, env=env, check=True, capture_output=True)
    tables = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert "dataset_catalog" not in tables and "holdout_generations" not in tables
    assert "events" in tables


def test_all_github_actions_are_pinned_to_full_sha():
    pattern = re.compile(r"uses:\s+([^\s]+)@([^\s#]+)")
    seen = 0
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        for action, ref in pattern.findall(workflow.read_text(encoding="utf-8")):
            seen += 1
            assert re.fullmatch(r"[0-9a-f]{40}", ref), f"floating action {action}@{ref} in {workflow.name}"
    assert seen >= 20


def test_v48_ui_remains_three_tabs_and_adds_clear_action():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert html.count('class="simple-tab') == 3
    assert 'id="todayAction"' in html
    assert 'id="evidenceAccelerationDetails"' in html
    assert "app.js?v=4.9.0" in html
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "renderEvidenceAcceleration" in js
    assert "MAX_VISIBLE_CARDS = 8" in js


def test_new_workflows_are_zero_credit_and_long_session_bounded():
    evidence = (ROOT / ".github" / "workflows" / "run-evidence-acceleration.yml").read_text(encoding="utf-8")
    assert "THE_ODDS_API_KEY" not in evidence
    assert "provider_credits_consumed" in evidence
    long_session = (ROOT / ".github" / "workflows" / "verify-long-session.yml").read_text(encoding="utf-8")
    assert "--long-session-seconds" in long_session
    script = (ROOT / "scripts" / "browser_smoke_test.py").read_text(encoding="utf-8")
    assert "dom_growth" in script and "resource_growth" in script and "--report-path" in script
