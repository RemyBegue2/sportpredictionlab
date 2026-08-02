from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import math

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from scipy.stats import poisson
from sklearn.metrics import accuracy_score, log_loss

from .common import (
    Evaluation,
    apply_temperature_multiclass,
    chronological_group_split_indices,
    expected_calibration_error,
    fit_temperature_multiclass,
    multiclass_brier,
    optimize_blend_multiclass,
    ranked_probability_score,
    safe_days_between,
    validate_date_order,
)

# Class order is away win, draw, home win. This makes RPS order natural.
CLASS_NAMES = ["away", "draw", "home"]


@dataclass
class FootballArtifacts:
    goal_home_model: Any
    goal_away_model: Any
    result_model: Any
    temperature: float
    blend_ml_weight: float
    rho: float
    feature_columns: list[str]
    categorical_columns: list[str]
    max_goals: int = 8


class FootballPredictor:
    required_columns = {"date", "league", "home_team", "away_team", "home_goals", "away_goals"}

    def __init__(self, rolling_window: int = 8, random_seed: int = 42):
        self.rolling_window = rolling_window
        self.random_seed = random_seed
        self.artifacts: FootballArtifacts | None = None
        self.evaluation_: Evaluation | None = None

    def build_features(self, matches: pd.DataFrame, allow_unplayed: bool = False) -> pd.DataFrame:
        missing = self.required_columns - set(matches.columns)
        if missing:
            raise ValueError(f"Missing football columns: {sorted(missing)}")
        df = validate_date_order(matches)

        elo = defaultdict(lambda: 1500.0)
        gf = defaultdict(lambda: deque(maxlen=self.rolling_window))
        ga = defaultdict(lambda: deque(maxlen=self.rolling_window))
        last_date: dict[str, pd.Timestamp] = {}
        games = defaultdict(int)
        league_home_goals = defaultdict(list)
        league_away_goals = defaultdict(list)

        rows: list[dict[str, Any]] = []
        # Results with an identical timestamp are applied as one batch. This is
        # conservative for date-only archives and prevents same-day look-ahead.
        for date, group in df.groupby("date", sort=False):
            updates: list[tuple[str, str, str, int, int]] = []
            elo_deltas: dict[str, float] = defaultdict(float)
            for row in group.itertuples(index=False):
                home = str(row.home_team)
                away = str(row.away_team)
                league = str(row.league)
                played = not pd.isna(row.home_goals) and not pd.isna(row.away_goals)
                if not played and not allow_unplayed:
                    raise ValueError("Unplayed football rows require allow_unplayed=True.")
                home_goals = int(row.home_goals) if played else np.nan
                away_goals = int(row.away_goals) if played else np.nan

                hgf = float(np.mean(gf[home])) if gf[home] else 1.35
                hga = float(np.mean(ga[home])) if ga[home] else 1.25
                agf = float(np.mean(gf[away])) if gf[away] else 1.10
                aga = float(np.mean(ga[away])) if ga[away] else 1.35
                lg_h = float(np.mean(league_home_goals[league])) if league_home_goals[league] else 1.45
                lg_a = float(np.mean(league_away_goals[league])) if league_away_goals[league] else 1.15

                elo_diff = elo[home] + 65.0 - elo[away]
                elo_home_prob = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
                rows.append({
                    "date": date,
                    "league": league,
                    "home_team": home,
                    "away_team": away,
                    "home_elo": elo[home],
                    "away_elo": elo[away],
                    "elo_diff": elo_diff,
                    "elo_home_prob": elo_home_prob,
                    "home_attack_form": hgf,
                    "home_defence_form": hga,
                    "away_attack_form": agf,
                    "away_defence_form": aga,
                    "league_home_goal_rate": lg_h,
                    "league_away_goal_rate": lg_a,
                    "home_rest_days": min(safe_days_between(date, last_date.get(home)), 60.0),
                    "away_rest_days": min(safe_days_between(date, last_date.get(away)), 60.0),
                    "home_matches_seen": games[home],
                    "away_matches_seen": games[away],
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "result_class": (2 if home_goals > away_goals else (1 if home_goals == away_goals else 0)) if played else np.nan,
                })

                if played:
                    expected_home = 1.0 / (1.0 + 10.0 ** (-(elo[home] + 65.0 - elo[away]) / 400.0))
                    actual_home = 1.0 if home_goals > away_goals else (0.5 if home_goals == away_goals else 0.0)
                    margin = abs(home_goals - away_goals)
                    k = 22.0 * (1.0 + 0.15 * min(margin, 4))
                    delta = k * (actual_home - expected_home)
                    elo_deltas[home] += delta
                    elo_deltas[away] -= delta
                    updates.append((home, away, league, home_goals, away_goals))

            for team, delta in elo_deltas.items():
                elo[team] += delta
            for home, away, league, home_goals, away_goals in updates:
                gf[home].append(home_goals)
                ga[home].append(away_goals)
                gf[away].append(away_goals)
                ga[away].append(home_goals)
                league_home_goals[league].append(home_goals)
                league_away_goals[league].append(away_goals)
                last_date[home] = date
                last_date[away] = date
                games[home] += 1
                games[away] += 1

        return pd.DataFrame(rows)

    @staticmethod
    def _score_matrix(lambda_home: float, lambda_away: float, rho: float, max_goals: int) -> np.ndarray:
        h = np.arange(max_goals + 1)
        a = np.arange(max_goals + 1)
        mat = np.outer(poisson.pmf(h, lambda_home), poisson.pmf(a, lambda_away))
        # Dixon-Coles low-score correction.
        corrections = {
            (0, 0): 1.0 - lambda_home * lambda_away * rho,
            (0, 1): 1.0 + lambda_home * rho,
            (1, 0): 1.0 + lambda_away * rho,
            (1, 1): 1.0 - rho,
        }
        for (i, j), factor in corrections.items():
            mat[i, j] *= max(factor, 1e-6)
        return mat / mat.sum()

    def _poisson_probs(self, lambdas_home: np.ndarray, lambdas_away: np.ndarray, rho: float, max_goals: int = 8) -> np.ndarray:
        result = []
        for lh, la in zip(lambdas_home, lambdas_away):
            mat = self._score_matrix(float(lh), float(la), rho, max_goals)
            home = float(np.tril(mat, -1).sum())
            draw = float(np.trace(mat))
            away = float(np.triu(mat, 1).sum())
            result.append([away, draw, home])
        return np.asarray(result)

    def _fit_rho(self, lambdas_home: np.ndarray, lambdas_away: np.ndarray, hg: np.ndarray, ag: np.ndarray) -> float:
        candidates = np.linspace(-0.15, 0.15, 61)
        losses = []
        for rho in candidates:
            nll = 0.0
            for lh, la, h, a in zip(lambdas_home, lambdas_away, hg, ag):
                max_g = max(8, int(h), int(a))
                mat = self._score_matrix(float(lh), float(la), float(rho), max_g)
                nll -= math.log(max(float(mat[int(h), int(a)]), 1e-12))
            losses.append(nll / len(hg))
        return float(candidates[int(np.argmin(losses))])

    def fit(self, matches: pd.DataFrame) -> Evaluation:
        feat = self.build_features(matches)
        train_s, cal_s, test_s = chronological_group_split_indices(feat["date"])
        categorical = ["league", "home_team", "away_team"]
        ignored = ["date", "home_goals", "away_goals", "result_class"]
        feature_cols = [c for c in feat.columns if c not in ignored]

        X_train, X_cal, X_test = feat.iloc[train_s][feature_cols], feat.iloc[cal_s][feature_cols], feat.iloc[test_s][feature_cols]
        y_h_train, y_h_cal = feat.iloc[train_s]["home_goals"], feat.iloc[cal_s]["home_goals"]
        y_a_train, y_a_cal = feat.iloc[train_s]["away_goals"], feat.iloc[cal_s]["away_goals"]
        y_r_train = feat.iloc[train_s]["result_class"].to_numpy()
        y_r_cal = feat.iloc[cal_s]["result_class"].to_numpy()
        y_r_test = feat.iloc[test_s]["result_class"].to_numpy()

        cat_idx = [feature_cols.index(c) for c in categorical]
        common_params = dict(iterations=260, depth=6, learning_rate=0.045, random_seed=self.random_seed, verbose=False, allow_writing_files=False)
        home_model = CatBoostRegressor(loss_function="Poisson", **common_params)
        away_model = CatBoostRegressor(loss_function="Poisson", **common_params)
        home_model.fit(X_train, y_h_train, cat_features=cat_idx)
        away_model.fit(X_train, y_a_train, cat_features=cat_idx)

        lh_cal = np.clip(home_model.predict(X_cal), 0.08, 5.5)
        la_cal = np.clip(away_model.predict(X_cal), 0.08, 5.5)
        rho = self._fit_rho(lh_cal, la_cal, y_h_cal.to_numpy(), y_a_cal.to_numpy())
        stat_cal = self._poisson_probs(lh_cal, la_cal, rho)

        result_model = CatBoostClassifier(loss_function="MultiClass", eval_metric="MultiClass", **common_params)
        result_model.fit(X_train, y_r_train, cat_features=cat_idx)
        ml_cal_raw = result_model.predict_proba(X_cal)
        temperature = fit_temperature_multiclass(ml_cal_raw, y_r_cal)
        ml_cal = apply_temperature_multiclass(ml_cal_raw, temperature)
        blend_weight = optimize_blend_multiclass(stat_cal, ml_cal, y_r_cal)

        lh_test = np.clip(home_model.predict(X_test), 0.08, 5.5)
        la_test = np.clip(away_model.predict(X_test), 0.08, 5.5)
        stat_test = self._poisson_probs(lh_test, la_test, rho)
        ml_test = apply_temperature_multiclass(result_model.predict_proba(X_test), temperature)
        final = blend_weight * ml_test + (1 - blend_weight) * stat_test

        train_prior = np.bincount(y_r_train, minlength=3).astype(float)
        train_prior /= train_prior.sum()
        naive_test = np.tile(train_prior, (len(y_r_test), 1))
        metrics = {
            "log_loss": float(log_loss(y_r_test, final, labels=[0, 1, 2])),
            "naive_log_loss": float(log_loss(y_r_test, naive_test, labels=[0, 1, 2])),
            "poisson_dc_log_loss": float(log_loss(y_r_test, stat_test, labels=[0, 1, 2])),
            "ml_only_log_loss": float(log_loss(y_r_test, ml_test, labels=[0, 1, 2])),
            "brier": multiclass_brier(y_r_test, final, 3),
            "rps": ranked_probability_score(y_r_test, final),
            "accuracy": float(accuracy_score(y_r_test, final.argmax(axis=1))),
            "ece": expected_calibration_error(y_r_test, final),
            "calibration_temperature": temperature,
            "ml_blend_weight": blend_weight,
            "dixon_coles_rho": rho,
        }
        self.artifacts = FootballArtifacts(home_model, away_model, result_model, temperature, blend_weight, rho, feature_cols, categorical)
        self.evaluation_ = Evaluation(metrics, len(y_r_test))
        return self.evaluation_


    def make_upcoming_features(self, history: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
        required = {"date", "league", "home_team", "away_team"}
        missing = required - set(fixtures.columns)
        if missing:
            raise ValueError(f"Missing fixture columns: {sorted(missing)}")
        hist = history.copy()
        fix = fixtures.copy()
        fix["home_goals"] = np.nan
        fix["away_goals"] = np.nan
        combined = pd.concat([hist, fix], ignore_index=True, sort=False)
        features = self.build_features(combined, allow_unplayed=True)
        upcoming = features[features["result_class"].isna()].copy()
        if len(upcoming) != len(fix):
            raise ValueError("History must contain completed matches only.")
        return upcoming.reset_index(drop=True)

    def predict_matches(self, history: pd.DataFrame, fixtures: pd.DataFrame, top_scores: int = 5) -> list[dict[str, Any]]:
        return self.predict_feature_rows(self.make_upcoming_features(history, fixtures), top_scores=top_scores)

    def predict_feature_rows(self, feature_rows: pd.DataFrame, top_scores: int = 5) -> list[dict[str, Any]]:
        if self.artifacts is None:
            raise RuntimeError("Fit or load the model first.")
        a = self.artifacts
        X = feature_rows[a.feature_columns].copy()
        lh = np.clip(a.goal_home_model.predict(X), 0.08, 5.5)
        la = np.clip(a.goal_away_model.predict(X), 0.08, 5.5)
        stat = self._poisson_probs(lh, la, a.rho, a.max_goals)
        ml = apply_temperature_multiclass(a.result_model.predict_proba(X), a.temperature)
        final = a.blend_ml_weight * ml + (1 - a.blend_ml_weight) * stat
        outputs = []
        for i, (p, h_lambda, a_lambda) in enumerate(zip(final, lh, la)):
            matrix = self._score_matrix(float(h_lambda), float(a_lambda), a.rho, a.max_goals)
            flat = np.argsort(matrix.ravel())[::-1][:top_scores]
            scores = []
            for idx in flat:
                hg, ag = np.unravel_index(idx, matrix.shape)
                scores.append({"score": f"{hg}-{ag}", "probability": float(matrix[hg, ag])})
            outputs.append({
                "away_win": float(p[0]),
                "draw": float(p[1]),
                "home_win": float(p[2]),
                "expected_home_goals": float(h_lambda),
                "expected_away_goals": float(a_lambda),
                "top_scores": scores,
            })
        return outputs

    def save(self, path: str | Path) -> None:
        if self.artifacts is None:
            raise RuntimeError("Nothing to save.")
        joblib.dump(self.artifacts, path)

    def load(self, path: str | Path) -> None:
        self.artifacts = joblib.load(path)
