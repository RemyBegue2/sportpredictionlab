from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score, log_loss

from .common import (
    Evaluation,
    apply_temperature_binary,
    binary_brier,
    chronological_group_split_indices,
    expected_calibration_error,
    fit_temperature_binary,
    optimize_blend_binary,
    safe_days_between,
    validate_date_order,
)


@dataclass
class TennisArtifacts:
    model: Any
    temperature: float
    blend_ml_weight: float
    feature_columns: list[str]
    categorical_columns: list[str]


class TennisPredictor:
    required_columns = {"date", "surface", "tournament_level", "winner_name", "loser_name"}

    def __init__(self, rolling_window: int = 12, random_seed: int = 42):
        self.rolling_window = rolling_window
        self.random_seed = random_seed
        self.artifacts: TennisArtifacts | None = None
        self.evaluation_: Evaluation | None = None

    def build_features(self, matches: pd.DataFrame) -> pd.DataFrame:
        missing = self.required_columns - set(matches.columns)
        if missing:
            raise ValueError(f"Missing tennis columns: {sorted(missing)}")
        df = validate_date_order(matches)
        if "best_of" not in df:
            df["best_of"] = 3
        if "tour" not in df:
            df["tour"] = "unknown"
        for col in ["winner_rank", "loser_rank", "winner_rank_points", "loser_rank_points"]:
            if col not in df:
                df[col] = np.nan
            df[col] = pd.to_numeric(df[col], errors="coerce")

        global_elo = defaultdict(lambda: 1500.0)
        surface_elo = defaultdict(lambda: defaultdict(lambda: 1500.0))
        recent = defaultdict(lambda: deque(maxlen=self.rolling_window))
        last_date: dict[str, pd.Timestamp] = {}
        matches_seen = defaultdict(int)

        rows: list[dict[str, Any]] = []
        row_index = 0
        # ATP archives commonly expose tournament start date rather than exact
        # match time. Treat each identical timestamp as simultaneous to avoid
        # using a later-round result to predict another row from that tournament.
        for date, group in df.groupby("date", sort=False):
            global_deltas: dict[str, float] = defaultdict(float)
            surface_deltas: dict[tuple[str, str], float] = defaultdict(float)
            updates: list[tuple[str, str]] = []
            for row in group.itertuples(index=False):
                winner = str(row.winner_name)
                loser = str(row.loser_name)
                surface = str(row.surface).lower()
                level = str(row.tournament_level)
                tour = str(row.tour)
                best_of = int(row.best_of)
                winner_rank = float(row.winner_rank) if not pd.isna(row.winner_rank) else 500.0
                loser_rank = float(row.loser_rank) if not pd.isna(row.loser_rank) else 500.0
                winner_points = float(row.winner_rank_points) if not pd.isna(row.winner_rank_points) else 0.0
                loser_points = float(row.loser_rank_points) if not pd.isna(row.loser_rank_points) else 0.0

                # Deterministic alternating orientation avoids winner-first leakage.
                if row_index % 2 == 0:
                    p1, p2, target = winner, loser, 1
                    p1_rank, p2_rank = winner_rank, loser_rank
                    p1_points, p2_points = winner_points, loser_points
                else:
                    p1, p2, target = loser, winner, 0
                    p1_rank, p2_rank = loser_rank, winner_rank
                    p1_points, p2_points = loser_points, winner_points
                row_index += 1

                gdiff = global_elo[p1] - global_elo[p2]
                sdiff = surface_elo[surface][p1] - surface_elo[surface][p2]
                combined_diff = 0.65 * gdiff + 0.35 * sdiff
                elo_prob = 1.0 / (1.0 + 10.0 ** (-combined_diff / 400.0))
                p1_recent = float(np.mean(recent[p1])) if recent[p1] else 0.5
                p2_recent = float(np.mean(recent[p2])) if recent[p2] else 0.5

                rows.append({
                    "date": date,
                    "tour": tour,
                    "surface": surface,
                    "tournament_level": level,
                    "best_of": best_of,
                    "player_1": p1,
                    "player_2": p2,
                    "p1_rank": p1_rank,
                    "p2_rank": p2_rank,
                    "rank_log_advantage": float(np.log1p(p2_rank) - np.log1p(p1_rank)),
                    "p1_rank_points": p1_points,
                    "p2_rank_points": p2_points,
                    "rank_points_diff": p1_points - p2_points,
                    "p1_global_elo": global_elo[p1],
                    "p2_global_elo": global_elo[p2],
                    "global_elo_diff": gdiff,
                    "p1_surface_elo": surface_elo[surface][p1],
                    "p2_surface_elo": surface_elo[surface][p2],
                    "surface_elo_diff": sdiff,
                    "combined_elo_diff": combined_diff,
                    "elo_probability": elo_prob,
                    "p1_recent_win_rate": p1_recent,
                    "p2_recent_win_rate": p2_recent,
                    "recent_form_diff": p1_recent - p2_recent,
                    "p1_inactivity_days": min(safe_days_between(date, last_date.get(p1)), 180.0),
                    "p2_inactivity_days": min(safe_days_between(date, last_date.get(p2)), 180.0),
                    "p1_matches_seen": matches_seen[p1],
                    "p2_matches_seen": matches_seen[p2],
                    "player1_win": target,
                })

                level_k = {"G": 34.0, "M": 30.0, "A": 26.0, "C": 22.0, "F": 20.0}.get(level, 24.0)
                exp_w = 1.0 / (1.0 + 10.0 ** (-(global_elo[winner] - global_elo[loser]) / 400.0))
                delta = level_k * (1.0 - exp_w)
                global_deltas[winner] += delta
                global_deltas[loser] -= delta

                exp_sw = 1.0 / (1.0 + 10.0 ** (-(surface_elo[surface][winner] - surface_elo[surface][loser]) / 400.0))
                sdelta = (level_k + 4.0) * (1.0 - exp_sw)
                surface_deltas[(surface, winner)] += sdelta
                surface_deltas[(surface, loser)] -= sdelta
                updates.append((winner, loser))

            for player, delta in global_deltas.items():
                global_elo[player] += delta
            for (surface, player), delta in surface_deltas.items():
                surface_elo[surface][player] += delta
            for winner, loser in updates:
                recent[winner].append(1.0)
                recent[loser].append(0.0)
                last_date[winner] = date
                last_date[loser] = date
                matches_seen[winner] += 1
                matches_seen[loser] += 1

        return pd.DataFrame(rows)

    @staticmethod
    def _swap_features(X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        pairs = [
            ("player_1", "player_2"),
            ("p1_global_elo", "p2_global_elo"),
            ("p1_surface_elo", "p2_surface_elo"),
            ("p1_recent_win_rate", "p2_recent_win_rate"),
            ("p1_inactivity_days", "p2_inactivity_days"),
            ("p1_matches_seen", "p2_matches_seen"),
            ("p1_rank", "p2_rank"),
            ("p1_rank_points", "p2_rank_points"),
        ]
        for a, b in pairs:
            tmp = out[a].copy()
            out[a] = out[b]
            out[b] = tmp
        for c in ["global_elo_diff", "surface_elo_diff", "combined_elo_diff", "recent_form_diff", "rank_log_advantage", "rank_points_diff"]:
            out[c] = -out[c]
        out["elo_probability"] = 1.0 - out["elo_probability"]
        return out

    def _symmetric_raw_probability(self, model: CatBoostClassifier, X: pd.DataFrame) -> np.ndarray:
        p_ab = model.predict_proba(X)[:, 1]
        p_ba = model.predict_proba(self._swap_features(X))[:, 1]
        return 0.5 * (p_ab + (1.0 - p_ba))

    def fit(self, matches: pd.DataFrame) -> Evaluation:
        feat = self.build_features(matches)
        train_s, cal_s, test_s = chronological_group_split_indices(feat["date"])
        categorical = ["tour", "surface", "tournament_level", "player_1", "player_2"]
        ignored = ["date", "player1_win"]
        feature_cols = [c for c in feat.columns if c not in ignored]

        X_train = feat.iloc[train_s][feature_cols]
        y_train = feat.iloc[train_s]["player1_win"].to_numpy()
        X_cal = feat.iloc[cal_s][feature_cols]
        y_cal = feat.iloc[cal_s]["player1_win"].to_numpy()
        X_test = feat.iloc[test_s][feature_cols]
        y_test = feat.iloc[test_s]["player1_win"].to_numpy()

        # Data augmentation explicitly enforces player-order symmetry.
        X_aug = pd.concat([X_train, self._swap_features(X_train)], ignore_index=True)
        y_aug = np.concatenate([y_train, 1 - y_train])
        cat_idx = [feature_cols.index(c) for c in categorical]
        model = CatBoostClassifier(
            iterations=320,
            depth=6,
            learning_rate=0.04,
            loss_function="Logloss",
            eval_metric="Logloss",
            random_seed=self.random_seed,
            verbose=False,
            allow_writing_files=False,
        )
        model.fit(X_aug, y_aug, cat_features=cat_idx)

        ml_cal_raw = self._symmetric_raw_probability(model, X_cal)
        temperature = fit_temperature_binary(ml_cal_raw, y_cal)
        ml_cal = apply_temperature_binary(ml_cal_raw, temperature)
        elo_cal = X_cal["elo_probability"].to_numpy(dtype=float)
        blend_weight = optimize_blend_binary(elo_cal, ml_cal, y_cal)

        ml_test = apply_temperature_binary(self._symmetric_raw_probability(model, X_test), temperature)
        elo_test = X_test["elo_probability"].to_numpy(dtype=float)
        final = blend_weight * ml_test + (1 - blend_weight) * elo_test
        swapped_final = blend_weight * apply_temperature_binary(self._symmetric_raw_probability(model, self._swap_features(X_test)), temperature) + (1 - blend_weight) * (1 - elo_test)
        symmetry_error = float(np.mean(np.abs(final + swapped_final - 1.0)))

        metrics = {
            "log_loss": float(log_loss(y_test, final, labels=[0, 1])),
            "naive_log_loss": float(log_loss(y_test, np.full(len(y_test), 0.5), labels=[0, 1])),
            "elo_only_log_loss": float(log_loss(y_test, elo_test, labels=[0, 1])),
            "ml_only_log_loss": float(log_loss(y_test, ml_test, labels=[0, 1])),
            "brier": binary_brier(y_test, final),
            "accuracy": float(accuracy_score(y_test, final >= 0.5)),
            "ece": expected_calibration_error(y_test, final),
            "symmetry_error": symmetry_error,
            "calibration_temperature": temperature,
            "ml_blend_weight": blend_weight,
        }
        self.artifacts = TennisArtifacts(model, temperature, blend_weight, feature_cols, categorical)
        self.evaluation_ = Evaluation(metrics, len(y_test))
        return self.evaluation_


    def fit_elo_only(self, matches: pd.DataFrame) -> Evaluation:
        """Create a conservative serving artifact when calibration is impossible.

        This is intended only for tiny smoke-test snapshots with too few distinct
        tournament dates. The CatBoost component is disabled and no performance
        claim is produced.
        """
        feat = self.build_features(matches)
        categorical = ["tour", "surface", "tournament_level", "player_1", "player_2"]
        ignored = ["date", "player1_win"]
        feature_cols = [c for c in feat.columns if c not in ignored]
        self.artifacts = TennisArtifacts(None, 1.0, 0.0, feature_cols, categorical)
        self.evaluation_ = Evaluation({
            "serving_mode": "elo_only_uncalibrated",
            "ml_blend_weight": 0.0,
            "calibration_temperature": 1.0,
            "symmetry_error": 0.0,
        }, 0)
        return self.evaluation_

    def make_upcoming_features(self, history: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
        missing = self.required_columns - set(history.columns)
        if missing:
            raise ValueError(f"Missing tennis history columns: {sorted(missing)}")
        fixture_required = {"date", "surface", "tournament_level", "player_1", "player_2"}
        missing_f = fixture_required - set(fixtures.columns)
        if missing_f:
            raise ValueError(f"Missing tennis fixture columns: {sorted(missing_f)}")
        hist = validate_date_order(history)
        fix = fixtures.copy()
        fix["date"] = pd.to_datetime(fix["date"], utc=True, errors="raise")
        fix["fixture_order"] = np.arange(len(fix))
        if "best_of" not in hist:
            hist["best_of"] = 3
        if "tour" not in hist:
            hist["tour"] = "unknown"
        for col in ["winner_rank", "loser_rank", "winner_rank_points", "loser_rank_points"]:
            if col not in hist:
                hist[col] = np.nan
            hist[col] = pd.to_numeric(hist[col], errors="coerce")
        if "best_of" not in fix:
            fix["best_of"] = 3
        if "tour" not in fix:
            fix["tour"] = "unknown"

        global_elo = defaultdict(lambda: 1500.0)
        surface_elo = defaultdict(lambda: defaultdict(lambda: 1500.0))
        recent = defaultdict(lambda: deque(maxlen=self.rolling_window))
        last_date: dict[str, pd.Timestamp] = {}
        matches_seen = defaultdict(int)
        latest_rank = defaultdict(lambda: 500.0)
        latest_points = defaultdict(float)

        history_groups = list(hist.groupby("date", sort=False))
        history_pos = 0

        def apply_history_group(date: pd.Timestamp, group: pd.DataFrame) -> None:
            global_deltas: dict[str, float] = defaultdict(float)
            surface_deltas: dict[tuple[str, str], float] = defaultdict(float)
            updates: list[tuple[str, str, float, float, float, float]] = []
            for row in group.itertuples(index=False):
                winner, loser = str(row.winner_name), str(row.loser_name)
                surface, level = str(row.surface).lower(), str(row.tournament_level)
                level_k = {"G": 34.0, "M": 30.0, "A": 26.0, "C": 22.0, "F": 20.0}.get(level, 24.0)
                exp_w = 1.0 / (1.0 + 10.0 ** (-(global_elo[winner] - global_elo[loser]) / 400.0))
                delta = level_k * (1.0 - exp_w)
                global_deltas[winner] += delta
                global_deltas[loser] -= delta
                exp_sw = 1.0 / (1.0 + 10.0 ** (-(surface_elo[surface][winner] - surface_elo[surface][loser]) / 400.0))
                sdelta = (level_k + 4.0) * (1.0 - exp_sw)
                surface_deltas[(surface, winner)] += sdelta
                surface_deltas[(surface, loser)] -= sdelta
                updates.append((winner, loser, row.winner_rank, row.loser_rank,
                                row.winner_rank_points, row.loser_rank_points))
            for player, delta in global_deltas.items():
                global_elo[player] += delta
            for (surface, player), delta in surface_deltas.items():
                surface_elo[surface][player] += delta
            for winner, loser, wr, lr, wp, lp in updates:
                recent[winner].append(1.0)
                recent[loser].append(0.0)
                last_date[winner] = date
                last_date[loser] = date
                matches_seen[winner] += 1
                matches_seen[loser] += 1
                if not pd.isna(wr):
                    latest_rank[winner] = float(wr)
                if not pd.isna(lr):
                    latest_rank[loser] = float(lr)
                if not pd.isna(wp):
                    latest_points[winner] = float(wp)
                if not pd.isna(lp):
                    latest_points[loser] = float(lp)

        rows: list[dict[str, Any]] = []
        for fixture_date, fixture_group in fix.sort_values(["date", "fixture_order"], kind="stable").groupby("date", sort=False):
            while history_pos < len(history_groups) and history_groups[history_pos][0] < fixture_date:
                hist_date, hist_group = history_groups[history_pos]
                apply_history_group(hist_date, hist_group)
                history_pos += 1

            for row in fixture_group.itertuples(index=False):
                p1, p2 = str(row.player_1), str(row.player_2)
                surface = str(row.surface).lower()
                gdiff = global_elo[p1] - global_elo[p2]
                sdiff = surface_elo[surface][p1] - surface_elo[surface][p2]
                combined_diff = 0.65 * gdiff + 0.35 * sdiff
                p1_recent = float(np.mean(recent[p1])) if recent[p1] else 0.5
                p2_recent = float(np.mean(recent[p2])) if recent[p2] else 0.5
                supplied_p1_rank = getattr(row, "p1_rank", np.nan)
                supplied_p2_rank = getattr(row, "p2_rank", np.nan)
                supplied_p1_points = getattr(row, "p1_rank_points", np.nan)
                supplied_p2_points = getattr(row, "p2_rank_points", np.nan)
                p1_rank = float(supplied_p1_rank) if not pd.isna(supplied_p1_rank) else latest_rank[p1]
                p2_rank = float(supplied_p2_rank) if not pd.isna(supplied_p2_rank) else latest_rank[p2]
                p1_points = float(supplied_p1_points) if not pd.isna(supplied_p1_points) else latest_points[p1]
                p2_points = float(supplied_p2_points) if not pd.isna(supplied_p2_points) else latest_points[p2]
                rows.append({
                    "fixture_order": row.fixture_order,
                    "date": fixture_date, "tour": str(row.tour), "surface": surface,
                    "tournament_level": str(row.tournament_level), "best_of": int(row.best_of),
                    "player_1": p1, "player_2": p2,
                    "p1_rank": p1_rank, "p2_rank": p2_rank,
                    "rank_log_advantage": float(np.log1p(p2_rank) - np.log1p(p1_rank)),
                    "p1_rank_points": p1_points, "p2_rank_points": p2_points,
                    "rank_points_diff": p1_points - p2_points,
                    "p1_global_elo": global_elo[p1], "p2_global_elo": global_elo[p2],
                    "global_elo_diff": gdiff,
                    "p1_surface_elo": surface_elo[surface][p1], "p2_surface_elo": surface_elo[surface][p2],
                    "surface_elo_diff": sdiff, "combined_elo_diff": combined_diff,
                    "elo_probability": 1.0 / (1.0 + 10.0 ** (-combined_diff / 400.0)),
                    "p1_recent_win_rate": p1_recent, "p2_recent_win_rate": p2_recent,
                    "recent_form_diff": p1_recent - p2_recent,
                    "p1_inactivity_days": min(safe_days_between(fixture_date, last_date.get(p1)), 180.0),
                    "p2_inactivity_days": min(safe_days_between(fixture_date, last_date.get(p2)), 180.0),
                    "p1_matches_seen": matches_seen[p1], "p2_matches_seen": matches_seen[p2],
                })
        return pd.DataFrame(rows).sort_values("fixture_order").drop(columns="fixture_order").reset_index(drop=True)

    def predict_matches(self, history: pd.DataFrame, fixtures: pd.DataFrame) -> np.ndarray:
        return self.predict_feature_rows(self.make_upcoming_features(history, fixtures))

    def predict_feature_rows(self, feature_rows: pd.DataFrame) -> np.ndarray:
        if self.artifacts is None:
            raise RuntimeError("Fit or load the model first.")
        a = self.artifacts
        X = feature_rows[a.feature_columns].copy()
        elo = X["elo_probability"].to_numpy(dtype=float)
        if a.blend_ml_weight <= 0.0 or a.model is None:
            return elo
        raw = self._symmetric_raw_probability(a.model, X)
        ml = apply_temperature_binary(raw, a.temperature)
        return a.blend_ml_weight * ml + (1 - a.blend_ml_weight) * elo

    def save(self, path: str | Path) -> None:
        if self.artifacts is None:
            raise RuntimeError("Nothing to save.")
        joblib.dump(self.artifacts, path)

    def load(self, path: str | Path) -> None:
        self.artifacts = joblib.load(path)
