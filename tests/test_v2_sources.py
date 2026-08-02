import pandas as pd
from sports_predictor.data_sources.football_data import FootballDataSource
from sports_predictor.data_sources.tennis_archive import TennisArchiveSource
from sports_predictor.market import devig_three_way

def test_football_normalization():
    raw=pd.DataFrame([{"Date":"11/08/2023","HomeTeam":"A","AwayTeam":"B","FTHG":2,"FTAG":1,"B365H":2.0,"B365D":3.2,"B365A":4.0}])
    out=FootballDataSource.normalize(raw,league="E0",season="2023-24")
    assert list(out[["home_team","away_team"]].iloc[0])==["A","B"]

def test_tennis_normalization():
    raw=pd.DataFrame([{"tourney_date":20250101,"surface":"Hard","tourney_level":"A","tourney_name":"X","winner_name":"A","loser_name":"B","best_of":3,"winner_rank":1,"loser_rank":2}])
    out=TennisArchiveSource.normalize(raw)
    assert out.iloc[0].surface=="hard"

def test_devig_sums_to_one():
    p=devig_three_way([2.0],[3.5],[4.0])
    assert abs(float(p.sum())-1)<1e-12

import pytest

def test_football_rejects_unsafe_league_code(tmp_path):
    source = FootballDataSource(cache_dir=tmp_path)
    with pytest.raises(ValueError, match="League code"):
        source.fetch("2023-24", "../../bad")
