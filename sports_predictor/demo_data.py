from __future__ import annotations

import numpy as np
import pandas as pd


def make_football_data(n_matches: int = 1000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    leagues = ["Ligue-1", "Premier-League"]
    teams_by_league = {
        "Ligue-1": [f"FR_{i:02d}" for i in range(16)],
        "Premier-League": [f"EN_{i:02d}" for i in range(16)],
    }
    attack = {t: rng.normal(0, 0.24) for teams in teams_by_league.values() for t in teams}
    defence = {t: rng.normal(0, 0.22) for teams in teams_by_league.values() for t in teams}
    rows = []
    date = pd.Timestamp("2021-08-01", tz="UTC")
    for i in range(n_matches):
        league = leagues[i % len(leagues)]
        teams = teams_by_league[league]
        home, away = rng.choice(teams, size=2, replace=False)
        # Slowly changing strengths create realistic non-stationarity.
        if i % 80 == 0 and i > 0:
            for team in teams:
                attack[team] += rng.normal(0, 0.025)
                defence[team] += rng.normal(0, 0.025)
        lh = np.exp(0.30 + attack[home] - defence[away] + 0.20)
        la = np.exp(0.13 + attack[away] - defence[home])
        hg = int(rng.poisson(np.clip(lh, 0.15, 4.5)))
        ag = int(rng.poisson(np.clip(la, 0.12, 4.0)))
        rows.append({"date": date, "league": league, "home_team": home, "away_team": away, "home_goals": hg, "away_goals": ag})
        date += pd.Timedelta(hours=int(rng.integers(18, 50)))
    return pd.DataFrame(rows)


def make_tennis_data(n_matches: int = 2200, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    players = [f"Player_{i:03d}" for i in range(90)]
    base = {p: rng.normal(0, 1.0) for p in players}
    surface_bonus = {s: {p: rng.normal(0, 0.35) for p in players} for s in ["hard", "clay", "grass"]}
    rows = []
    date = pd.Timestamp("2020-01-01", tz="UTC")
    levels = np.array(["G", "M", "A", "C"])
    for i in range(n_matches):
        surface = rng.choice(["hard", "clay", "grass"], p=[0.55, 0.32, 0.13])
        p1, p2 = rng.choice(players, 2, replace=False)
        if i % 150 == 0 and i > 0:
            for p in players:
                base[p] += rng.normal(0, 0.05)
        latent = (base[p1] + surface_bonus[surface][p1]) - (base[p2] + surface_bonus[surface][p2])
        prob = 1.0 / (1.0 + np.exp(-latent))
        winner, loser = (p1, p2) if rng.random() < prob else (p2, p1)
        level = str(rng.choice(levels, p=[0.12, 0.20, 0.48, 0.20]))
        rows.append({
            "date": date,
            "tour": "ATP-demo",
            "surface": surface,
            "tournament_level": level,
            "best_of": 5 if level == "G" and rng.random() < 0.45 else 3,
            "winner_name": winner,
            "loser_name": loser,
        })
        date += pd.Timedelta(hours=int(rng.integers(5, 20)))
    return pd.DataFrame(rows)
