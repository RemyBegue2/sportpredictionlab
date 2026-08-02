from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

import pandas as pd

from .identity import football_model_name, normalize_identity


@dataclass(frozen=True)
class MatchCandidate:
    provider_event_id: str
    result_index: int | str
    confidence: float
    status: str
    reason: str
    home_similarity: float
    away_similarity: float
    time_delta_minutes: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _similarity(left: Any, right: Any) -> float:
    left_text = str(left or "")
    right_text = str(right or "")
    left_variants = {normalize_identity(left_text), normalize_identity(football_model_name(left_text))}
    right_variants = {normalize_identity(right_text), normalize_identity(football_model_name(right_text))}
    best = 0.0
    for a in left_variants:
        for b in right_variants:
            if not a or not b:
                continue
            if a == b:
                return 1.0
            a_tokens = set(a.split())
            b_tokens = set(b.split())
            token_score = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
            sequence_score = SequenceMatcher(None, a, b).ratio()
            best = max(best, token_score, sequence_score)
    return float(best)


def _utc(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True, errors="raise")


def match_event_to_results(
    event: Mapping[str, Any],
    results: pd.DataFrame,
    *,
    sport: str = "football",
    max_time_delta_hours: float = 36.0,
    minimum_confidence: float = 0.90,
    ambiguity_gap: float = 0.04,
) -> MatchCandidate:
    required = {"date", "home_team", "away_team"}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"Missing result columns: {sorted(missing)}")
    provider_id = str(event.get("event_id") or event.get("id") or "").strip()
    if not provider_id:
        raise ValueError("provider event id is required")
    event_time = _utc(event.get("commence_time"))
    frame = results.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame = frame[frame["date"].notna()].copy()
    frame["_delta_minutes"] = (frame["date"] - event_time).abs().dt.total_seconds() / 60.0
    frame = frame[frame["_delta_minutes"] <= float(max_time_delta_hours) * 60.0]
    if frame.empty:
        return MatchCandidate(provider_id, -1, 0.0, "unmatched", "no result inside the time window", 0.0, 0.0, float("inf"))

    home_name = event.get("home_team")
    away_name = event.get("away_team")
    candidates: list[tuple[float, float, float, float, Any]] = []
    for index, row in frame.iterrows():
        direct_home = _similarity(home_name, row["home_team"])
        direct_away = _similarity(away_name, row["away_team"])
        direct = (direct_home + direct_away) / 2.0
        if sport == "tennis":
            swapped_home = _similarity(home_name, row["away_team"])
            swapped_away = _similarity(away_name, row["home_team"])
            swapped = (swapped_home + swapped_away) / 2.0
            if swapped > direct:
                direct, direct_home, direct_away = swapped, swapped_home, swapped_away
        time_score = max(0.0, 1.0 - float(row["_delta_minutes"]) / (float(max_time_delta_hours) * 60.0))
        confidence = 0.88 * direct + 0.12 * time_score
        candidates.append((confidence, direct_home, direct_away, float(row["_delta_minutes"]), index))

    candidates.sort(key=lambda item: item[0], reverse=True)
    best = candidates[0]
    second = candidates[1][0] if len(candidates) > 1 else -1.0
    if best[0] < minimum_confidence:
        status = "unmatched"
        reason = "best identity score below threshold"
    elif second >= 0 and best[0] - second < ambiguity_gap:
        status = "ambiguous"
        reason = "multiple result rows have near-identical scores"
    else:
        status = "matched"
        reason = "identity and time checks passed"
    return MatchCandidate(provider_id, best[4], float(best[0]), status, reason, float(best[1]), float(best[2]), float(best[3]))


def match_events_to_results(
    events: pd.DataFrame,
    results: pd.DataFrame,
    *,
    sport: str = "football",
    max_time_delta_hours: float = 36.0,
    minimum_confidence: float = 0.90,
    ambiguity_gap: float = 0.04,
) -> pd.DataFrame:
    required = {"event_id", "commence_time", "home_team", "away_team"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")
    rows = []
    for event in events.to_dict(orient="records"):
        candidate = match_event_to_results(
            event,
            results,
            sport=sport,
            max_time_delta_hours=max_time_delta_hours,
            minimum_confidence=minimum_confidence,
            ambiguity_gap=ambiguity_gap,
        )
        row = candidate.to_dict()
        row.update({
            "event_commence_time": pd.to_datetime(event["commence_time"], utc=True, errors="coerce"),
            "provider_home_team": event["home_team"],
            "provider_away_team": event["away_team"],
        })
        if candidate.status == "matched":
            result = results.loc[candidate.result_index]
            row.update({
                "result_date": pd.to_datetime(result["date"], utc=True, errors="coerce"),
                "result_home_team": result["home_team"],
                "result_away_team": result["away_team"],
                "home_goals": result.get("home_goals"),
                "away_goals": result.get("away_goals"),
            })
        rows.append(row)
    return pd.DataFrame(rows)
