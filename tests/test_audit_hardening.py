from pathlib import Path

import pandas as pd
import pytest

from sports_predictor.artifacts import verify_artifact_manifest, write_artifact_manifest
from sports_predictor.common import chronological_group_split_indices
from sports_predictor.data_sources.tennis_archive import TennisArchiveSource
from sports_predictor.football import FootballPredictor
from sports_predictor.tennis import TennisPredictor
from webapp import app
from fastapi.testclient import TestClient


def test_grouped_split_never_cuts_timestamp():
    dates = pd.to_datetime(
        ["2024-01-01"] * 12 + ["2024-01-02"] * 8 + ["2024-01-03"] * 7 +
        ["2024-01-04"] * 6 + ["2024-01-05"] * 7,
        utc=True,
    )
    train, calibration, test = chronological_group_split_indices(dates)
    assert dates[train.stop - 1] < dates[calibration.start]
    assert dates[calibration.stop - 1] < dates[test.start]


def test_football_same_timestamp_is_not_revealed_sequentially():
    matches = pd.DataFrame([
        {"date": "2024-01-01", "league": "X", "home_team": "A", "away_team": "B", "home_goals": 5, "away_goals": 0},
        {"date": "2024-01-01", "league": "X", "home_team": "C", "away_team": "D", "home_goals": 0, "away_goals": 1},
        {"date": "2024-01-02", "league": "X", "home_team": "A", "away_team": "C", "home_goals": 1, "away_goals": 1},
    ])
    feat = FootballPredictor().build_features(matches)
    assert feat.loc[0, "league_home_goal_rate"] == feat.loc[1, "league_home_goal_rate"] == 1.45
    assert feat.loc[0, "home_matches_seen"] == feat.loc[1, "home_matches_seen"] == 0
    assert feat.loc[2, "home_matches_seen"] == 1


def test_tennis_tournament_timestamp_is_batched():
    matches = pd.DataFrame([
        {"date": "2024-01-01", "tour": "ATP", "surface": "hard", "tournament_level": "A", "winner_name": "A", "loser_name": "B"},
        {"date": "2024-01-01", "tour": "ATP", "surface": "hard", "tournament_level": "A", "winner_name": "A", "loser_name": "C"},
        {"date": "2024-01-08", "tour": "ATP", "surface": "hard", "tournament_level": "A", "winner_name": "A", "loser_name": "D"},
    ])
    feat = TennisPredictor().build_features(matches)
    assert feat.loc[0, "p1_matches_seen"] == 0
    # The second row has reversed orientation, so A is player_2; its first same-date
    # result must still be invisible.
    assert feat.loc[1, "p2_matches_seen"] == 0
    assert max(feat.loc[2, "p1_matches_seen"], feat.loc[2, "p2_matches_seen"]) == 2


def test_tennis_normalizer_filters_non_completed_matches():
    raw = pd.DataFrame([
        {"tourney_date": 20250101, "surface": "Hard", "tourney_level": "A", "tourney_name": "X", "round": "R32", "winner_name": "A", "loser_name": "B", "score": "6-4 2-1 RET"},
        {"tourney_date": 20250101, "surface": "Hard", "tourney_level": "A", "tourney_name": "X", "round": "R32", "winner_name": "C", "loser_name": "D", "score": "6-4 6-4"},
    ])
    out = TennisArchiveSource.normalize(raw)
    assert list(out["winner_name"]) == ["C"]
    assert set(out["match_status"]) == {"completed"}


def test_artifact_manifest_detects_tampering(tmp_path: Path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"trusted")
    manifest = tmp_path / "manifest.json"
    write_artifact_manifest([artifact], manifest)
    verify_artifact_manifest(tmp_path, manifest)
    artifact.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="integrity"):
        verify_artifact_manifest(tmp_path, manifest)


def test_api_rejects_backcast_and_invalid_best_of():
    client = TestClient(app)
    backcast = client.post("/api/football/predict", json={
        "home_team": "Arsenal", "away_team": "Man City", "date": "2023-08-01"
    })
    assert backcast.status_code == 422
    invalid = client.post("/api/tennis/predict", json={
        "player_1": "Taylor Fritz", "player_2": "Alexander Zverev", "surface": "hard", "best_of": 4
    })
    assert invalid.status_code == 422
