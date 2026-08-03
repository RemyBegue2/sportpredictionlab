from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import brentq


@dataclass(frozen=True)
class DeviggedMarket:
    labels: list[str]
    odds: list[float]
    probabilities: list[float]
    overround: float
    method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_odds(odds: Sequence[float]) -> np.ndarray:
    values = np.asarray(odds, dtype=float)
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("At least two decimal odds are required")
    if not np.isfinite(values).all() or (values <= 1.0).any():
        raise ValueError("Decimal odds must be finite and greater than 1")
    return values


def devig_market(labels: Sequence[str], odds: Sequence[float], *, method: str = "power") -> DeviggedMarket:
    values = _validate_odds(odds)
    if len(labels) != len(values):
        raise ValueError("labels and odds must have the same length")
    implied = 1.0 / values
    overround = float(implied.sum() - 1.0)
    if method == "proportional" or overround <= 0:
        probabilities = implied / implied.sum()
        used_method = "proportional"
    elif method == "power":
        def objective(exponent: float) -> float:
            return float(np.power(implied, exponent).sum() - 1.0)

        try:
            exponent = brentq(objective, 0.01, 20.0)
            probabilities = np.power(implied, exponent)
            probabilities /= probabilities.sum()
            used_method = "power"
        except ValueError:
            probabilities = implied / implied.sum()
            used_method = "proportional_fallback"
    else:
        raise ValueError("method must be 'power' or 'proportional'")
    return DeviggedMarket(
        labels=[str(x) for x in labels],
        odds=[float(x) for x in values],
        probabilities=[float(x) for x in probabilities],
        overround=overround,
        method=used_method,
    )


def normalize_odds_payload(payload: Any) -> pd.DataFrame:
    """Normalize current or historical The Odds API payload to long rows."""
    snapshot_timestamp: str | None = None
    events = payload
    if isinstance(payload, Mapping) and "data" in payload:
        snapshot_timestamp = payload.get("timestamp")
        events = payload.get("data", [])
    rows: list[dict[str, Any]] = []
    for event in events or []:
        for bookmaker in event.get("bookmakers", []) or []:
            for market in bookmaker.get("markets", []) or []:
                for outcome in market.get("outcomes", []) or []:
                    rows.append({
                        "event_id": event.get("id"),
                        "sport_key": event.get("sport_key"),
                        "sport_title": event.get("sport_title"),
                        "commence_time": event.get("commence_time"),
                        "home_team": event.get("home_team"),
                        "away_team": event.get("away_team"),
                        "bookmaker_key": bookmaker.get("key"),
                        "bookmaker_title": bookmaker.get("title"),
                        "bookmaker_last_update": bookmaker.get("last_update"),
                        "market_key": market.get("key"),
                        "market_last_update": market.get("last_update") or bookmaker.get("last_update"),
                        "outcome_name": outcome.get("name"),
                        "price": outcome.get("price"),
                        "point": outcome.get("point"),
                        "description": outcome.get("description"),
                        "snapshot_time": snapshot_timestamp,
                    })
    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ("commence_time", "bookmaker_last_update", "market_last_update", "snapshot_time"):
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce", format="mixed")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df


def _ordered_h2h_labels(group: pd.DataFrame) -> list[str]:
    home = str(group["home_team"].iloc[0])
    away = str(group["away_team"].iloc[0])
    names = set(group["outcome_name"].astype(str))
    labels = [home]
    if "Draw" in names:
        labels.append("Draw")
    labels.append(away)
    return labels


def bookmaker_h2h_markets(rows: pd.DataFrame, *, method: str = "power") -> list[dict[str, Any]]:
    if rows.empty:
        return []
    data = rows[rows["market_key"].eq("h2h") & rows["price"].notna()].copy()
    results: list[dict[str, Any]] = []
    snapshot_column = next((col for col in ("requested_snapshot_at", "snapshot_time") if col in data.columns), None)
    keys = ["event_id", "bookmaker_key"] + ([snapshot_column] if snapshot_column else [])
    for _, group in data.groupby(keys, dropna=False, sort=False):
        labels = _ordered_h2h_labels(group)
        price_by_name = dict(zip(group["outcome_name"].astype(str), group["price"].astype(float), strict=False))
        if any(label not in price_by_name for label in labels):
            continue
        market = devig_market(labels, [price_by_name[label] for label in labels], method=method)
        probs = dict(zip(market.labels, market.probabilities, strict=True))
        odds = dict(zip(market.labels, market.odds, strict=True))
        results.append({
            "event_id": group["event_id"].iloc[0],
            "sport_key": group["sport_key"].iloc[0],
            "commence_time": group["commence_time"].iloc[0],
            "home_team": group["home_team"].iloc[0],
            "away_team": group["away_team"].iloc[0],
            "bookmaker_key": group["bookmaker_key"].iloc[0],
            "bookmaker_title": group["bookmaker_title"].iloc[0],
            "last_update": group["market_last_update"].max(),
            "snapshot_time": group["snapshot_time"].max(),
            "requested_snapshot_at": group[snapshot_column].iloc[0] if snapshot_column else group["snapshot_time"].max(),
            "labels": labels,
            "odds": odds,
            "probabilities": probs,
            "overround": market.overround,
            "devig_method": market.method,
        })
    return results


def consensus_h2h(
    markets: Sequence[Mapping[str, Any]],
    *,
    exclude: Iterable[str] = (),
    minimum_bookmakers: int = 2,
) -> dict[str, Any] | None:
    excluded = set(exclude)
    usable = [m for m in markets if m.get("bookmaker_key") not in excluded]
    if not usable:
        return None
    labels = list(usable[0]["labels"])
    aligned = []
    for market in usable:
        probs = market["probabilities"]
        if all(label in probs for label in labels):
            aligned.append([float(probs[label]) for label in labels])
    if len(aligned) < int(minimum_bookmakers):
        return None
    matrix = np.asarray(aligned, dtype=float)
    median = np.median(matrix, axis=0)
    median /= median.sum()
    return {
        "labels": labels,
        "probabilities": dict(zip(labels, [float(x) for x in median], strict=True)),
        "bookmaker_count": len(aligned),
        "method": "median_of_power_devigged_books",
    }


def closing_line_value(*, taken_odds: float, closing_odds: float) -> dict[str, float]:
    taken = float(taken_odds)
    closing = float(closing_odds)
    if taken <= 1.0 or closing <= 1.0:
        raise ValueError("Odds must be greater than 1")
    return {
        "odds_ratio": taken / closing,
        "log_clv": math.log(taken / closing),
        "implied_probability_change": (1.0 / closing) - (1.0 / taken),
    }


def market_age_minutes(last_update: Any, *, now: datetime | None = None) -> float | None:
    parsed = pd.to_datetime(last_update, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    reference = now or datetime.now(timezone.utc)
    return max(0.0, (reference - parsed.to_pydatetime()).total_seconds() / 60.0)


def normalize_scores_payload(payload: Any) -> pd.DataFrame:
    """Normalize The Odds API scores response to completed event rows."""
    events = payload.get("data", []) if isinstance(payload, Mapping) and "data" in payload else payload
    rows: list[dict[str, Any]] = []
    for event in events or []:
        score_map = {
            str(item.get("name")): item.get("score")
            for item in event.get("scores", []) or []
            if item.get("name") is not None
        }
        home = str(event.get("home_team") or "")
        away = str(event.get("away_team") or "")
        home_score = pd.to_numeric(score_map.get(home), errors="coerce")
        away_score = pd.to_numeric(score_map.get(away), errors="coerce")
        rows.append({
            "event_id": event.get("id"),
            "sport_key": event.get("sport_key"),
            "commence_time": event.get("commence_time"),
            "completed": bool(event.get("completed")),
            "home_team": home,
            "away_team": away,
            "home_score": home_score,
            "away_score": away_score,
            "last_update": event.get("last_update"),
        })
    frame = pd.DataFrame(rows)
    if not frame.empty:
        for col in ("commence_time", "last_update"):
            frame[col] = pd.to_datetime(frame[col], utc=True, errors="coerce", format="mixed")
        for col in ("home_score", "away_score"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame
