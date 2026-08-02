from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .event_matching import match_events_to_results
from .football import FootballPredictor
from .odds_data import bookmaker_h2h_markets, consensus_h2h


@dataclass(frozen=True)
class PreparationReport:
    events: int
    matched_events: int
    ambiguous_events: int
    unmatched_events: int
    model_predictions: int
    complete_market_rows: int
    benchmark_rows: int


def _result_class(home_goals: Any, away_goals: Any) -> int:
    home = int(home_goals)
    away = int(away_goals)
    return 2 if home > away else (1 if home == away else 0)


def generate_football_walkforward_predictions(
    results: pd.DataFrame,
    *,
    initial_train: int = 300,
    horizon: int = 100,
    max_folds: int = 20,
) -> pd.DataFrame:
    required = {"date", "league", "home_team", "away_team", "home_goals", "away_goals"}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"Missing football result columns: {sorted(missing)}")
    frame = results.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame = frame.dropna(subset=list(required)).sort_values("date", kind="stable").reset_index().rename(columns={"index": "result_index"})
    if initial_train < 30 or initial_train >= len(frame):
        raise ValueError("initial_train must be >=30 and smaller than the result dataset")
    boundaries = np.flatnonzero(frame["date"].to_numpy()[1:] != frame["date"].to_numpy()[:-1]) + 1
    boundaries = np.concatenate(([0], boundaries, [len(frame)]))
    candidates = boundaries[(boundaries >= initial_train) & (boundaries < len(frame))]
    if not len(candidates):
        raise ValueError("not enough distinct timestamps after the initial training window")
    start = int(candidates[0])
    predictions: list[dict[str, Any]] = []
    for fold in range(max_folds):
        if start >= len(frame):
            break
        desired = min(start + horizon, len(frame))
        end_candidates = boundaries[(boundaries > start) & (boundaries <= desired)]
        end = int(end_candidates[-1]) if len(end_candidates) else int(boundaries[boundaries > start][0])
        train = frame.iloc[:start].drop(columns=["result_index"]).copy()
        test = frame.iloc[start:end].copy()
        model = FootballPredictor()
        model.fit(train)
        rolling_history = train.copy()
        for timestamp, group in test.groupby("date", sort=False):
            fixtures = group[["date", "league", "home_team", "away_team"]].copy()
            outputs = model.predict_matches(rolling_history, fixtures)
            for (_, row), output in zip(group.iterrows(), outputs, strict=True):
                predictions.append({
                    "result_index": int(row["result_index"]),
                    "fold": fold + 1,
                    "commence_time": timestamp,
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "result_class": _result_class(row["home_goals"], row["away_goals"]),
                    "model_away": float(output["away_win"]),
                    "model_draw": float(output["draw"]),
                    "model_home": float(output["home_win"]),
                })
            rolling_history = pd.concat([rolling_history, group.drop(columns=["result_index"])], ignore_index=True)
        start = end
    return pd.DataFrame(predictions)


def _stage_markets(odds_rows: pd.DataFrame, target_stage: str | None) -> list[dict[str, Any]]:
    rows = odds_rows.copy()
    if "requested_snapshot_at" not in rows.columns:
        rows["requested_snapshot_at"] = rows.get("snapshot_time")
    rows["requested_snapshot_at"] = pd.to_datetime(rows["requested_snapshot_at"], utc=True, errors="coerce")
    if target_stage is not None and "stage" in rows.columns:
        rows = rows[rows["stage"].astype(str) == target_stage]
    return bookmaker_h2h_markets(rows)


def prepare_football_market_benchmark(
    *,
    results: pd.DataFrame,
    provider_events: pd.DataFrame,
    odds_rows: pd.DataFrame,
    target_stage: str | None = "t-1h",
    initial_train: int = 300,
    horizon: int = 100,
    max_folds: int = 20,
    winamax_key: str = "winamax_fr",
) -> tuple[pd.DataFrame, pd.DataFrame, PreparationReport]:
    mapping = match_events_to_results(provider_events, results, sport="football")
    model_predictions = generate_football_walkforward_predictions(
        results,
        initial_train=initial_train,
        horizon=horizon,
        max_folds=max_folds,
    )
    matched = mapping[mapping["status"].eq("matched")].copy()
    if matched.empty:
        report = PreparationReport(len(provider_events), 0, int(mapping["status"].eq("ambiguous").sum()), int(mapping["status"].eq("unmatched").sum()), len(model_predictions), 0, 0)
        return pd.DataFrame(), mapping, report
    matched["result_index"] = pd.to_numeric(matched["result_index"], errors="raise").astype(int)
    event_model = matched.merge(model_predictions, on="result_index", how="inner", suffixes=("_provider", "_model"))

    markets = _stage_markets(odds_rows, target_stage)
    market_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for market in markets:
        snapshot = pd.to_datetime(market.get("requested_snapshot_at") or market.get("snapshot_time"), utc=True, errors="coerce")
        key = (str(market["event_id"]), snapshot.isoformat() if not pd.isna(snapshot) else "missing")
        market_groups.setdefault(key, []).append(market)

    rows: list[dict[str, Any]] = []
    for _, event in event_model.iterrows():
        event_id = str(event["provider_event_id"])
        event_keys = sorted([key for key in market_groups if key[0] == event_id], key=lambda item: item[1])
        for key in event_keys:
            books = market_groups[key]
            winamax = next((book for book in books if book["bookmaker_key"] == winamax_key), None)
            consensus = consensus_h2h(books, exclude=(winamax_key,))
            if not winamax or not consensus:
                continue
            home = str(event["provider_home_team"])
            away = str(event["provider_away_team"])
            required_labels = [away, "Draw", home]
            if not all(label in winamax["probabilities"] and label in consensus["probabilities"] for label in required_labels):
                continue
            snapshot_at = pd.to_datetime(key[1], utc=True, errors="coerce")
            observed_at = pd.to_datetime(winamax.get("last_update") or snapshot_at, utc=True, errors="coerce")
            commence = pd.to_datetime(event["event_commence_time"], utc=True, errors="coerce")
            if pd.isna(observed_at) or pd.isna(commence) or observed_at >= commence:
                continue
            prediction_created_at = max(observed_at, snapshot_at) if not pd.isna(snapshot_at) else observed_at
            rows.append({
                "event_id": event_id,
                "stage": target_stage or "all",
                "commence_time": commence,
                "prediction_created_at": prediction_created_at,
                "odds_observed_at": observed_at,
                "result_available_at": commence + pd.Timedelta(hours=4),
                "home_team": home,
                "away_team": away,
                "result_class": int(event["result_class"]),
                "model_away": float(event["model_away"]),
                "model_draw": float(event["model_draw"]),
                "model_home": float(event["model_home"]),
                "winamax_away": float(winamax["probabilities"][away]),
                "winamax_draw": float(winamax["probabilities"]["Draw"]),
                "winamax_home": float(winamax["probabilities"][home]),
                "consensus_away": float(consensus["probabilities"][away]),
                "consensus_draw": float(consensus["probabilities"]["Draw"]),
                "consensus_home": float(consensus["probabilities"][home]),
                "winamax_away_odds": float(winamax["odds"][away]),
                "winamax_draw_odds": float(winamax["odds"]["Draw"]),
                "winamax_home_odds": float(winamax["odds"][home]),
                "winamax_overround": float(winamax["overround"]),
                "consensus_bookmakers": int(consensus["bookmaker_count"]),
                "identity_confidence": float(event["confidence"]),
                "model_fold": int(event["fold"]),
            })
    prepared = pd.DataFrame(rows)
    report = PreparationReport(
        events=len(provider_events),
        matched_events=int(mapping["status"].eq("matched").sum()),
        ambiguous_events=int(mapping["status"].eq("ambiguous").sum()),
        unmatched_events=int(mapping["status"].eq("unmatched").sum()),
        model_predictions=len(model_predictions),
        complete_market_rows=len(markets),
        benchmark_rows=len(prepared),
    )
    return prepared, mapping, report
