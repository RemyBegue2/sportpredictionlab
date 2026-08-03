from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from typing import Any, Sequence


MAX_SAMPLE_EVENTS = 30
MAX_DISCOVERY_CALLS = 31
MAX_ODDS_CREDITS = 200
SUPPORTED_SPORT_KEYS = {"soccer_epl"}
SUPPORTED_MARKETS = {"h2h"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _normalized_strings(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class SampleRequestPlan:
    schema_version: str
    sport_key: str
    start_date: str
    end_date: str
    sample_events: int
    horizons_hours: tuple[float, ...]
    markets: tuple[str, ...]
    bookmakers: tuple[str, ...]
    max_discovery_calls: int
    max_odds_credits: int
    estimated_discovery_calls: int
    estimated_snapshot_requests_upper_bound: int
    estimated_credits_upper_bound: int
    plan_request_id: str
    consumes_credits: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["horizons_hours"] = list(self.horizons_hours)
        value["markets"] = list(self.markets)
        value["bookmakers"] = list(self.bookmakers)
        return value


def build_sample_request_plan(
    *,
    sport_key: str,
    start_date: str,
    end_date: str,
    sample_events: int = 30,
    horizons_hours: Sequence[float] = (1.0,),
    markets: Sequence[str] = ("h2h",),
    bookmakers: Sequence[str] = ("winamax_fr", "betclic_fr", "unibet_fr", "pmu_fr", "pinnacle"),
    max_discovery_calls: int = 14,
    max_odds_credits: int = 120,
) -> SampleRequestPlan:
    if sport_key not in SUPPORTED_SPORT_KEYS:
        raise ValueError(f"unsupported sport_key: {sport_key}")
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must not precede start_date")
    discovery_calls = (end - start).days + 1
    if not 1 <= int(sample_events) <= MAX_SAMPLE_EVENTS:
        raise ValueError(f"sample_events must be between 1 and {MAX_SAMPLE_EVENTS}")
    if not 1 <= int(max_discovery_calls) <= MAX_DISCOVERY_CALLS:
        raise ValueError(f"max_discovery_calls must be between 1 and {MAX_DISCOVERY_CALLS}")
    if discovery_calls > int(max_discovery_calls):
        raise ValueError(f"date range requires {discovery_calls} discovery calls, cap is {max_discovery_calls}")
    if not 1 <= int(max_odds_credits) <= MAX_ODDS_CREDITS:
        raise ValueError(f"max_odds_credits must be between 1 and {MAX_ODDS_CREDITS}")
    normalized_horizons = tuple(sorted({float(value) for value in horizons_hours}))
    if not normalized_horizons or any(value <= 0 or value > 72 for value in normalized_horizons):
        raise ValueError("horizons_hours must contain values in ]0, 72]")
    normalized_markets = _normalized_strings(markets)
    if not normalized_markets or not set(normalized_markets).issubset(SUPPORTED_MARKETS):
        raise ValueError("only h2h is supported for the controlled sample")
    normalized_bookmakers = _normalized_strings(bookmakers)
    if "winamax_fr" not in normalized_bookmakers:
        raise ValueError("winamax_fr is required for the controlled sample")

    # One request per event and horizon, plus one closing snapshot per event.
    snapshot_upper = int(sample_events) * (len(normalized_horizons) + 1)
    identity = {
        "schema_version": "1.0",
        "sport_key": sport_key,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "sample_events": int(sample_events),
        "horizons_hours": list(normalized_horizons),
        "markets": list(normalized_markets),
        "bookmakers": list(normalized_bookmakers),
        "max_discovery_calls": int(max_discovery_calls),
        "max_odds_credits": int(max_odds_credits),
        "estimated_discovery_calls": int(discovery_calls),
        "estimated_snapshot_requests_upper_bound": snapshot_upper,
        "estimated_credits_upper_bound": int(max_odds_credits),
    }
    plan_request_id = "REQ-" + hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()[:24].upper()
    return SampleRequestPlan(**identity, plan_request_id=plan_request_id)


def validate_plan_request_id(plan: SampleRequestPlan, supplied: str) -> None:
    if not supplied or supplied.strip() != plan.plan_request_id:
        raise ValueError("plan_request_id does not match the immutable zero-credit estimate")
