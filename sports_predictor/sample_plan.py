from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
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


def select_discovery_dates(
    start_date: str | date,
    end_date: str | date,
    max_calls: int,
) -> tuple[date, ...]:
    """Return a deterministic, evenly spread discovery schedule.

    A long historical range must never turn into one provider call per calendar
    day. When the requested range is wider than the hard call cap, the schedule
    includes the first and last day and spreads the remaining calls over the
    interval. This keeps the provider budget bounded while sampling the whole
    requested period.
    """

    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    if end < start:
        raise ValueError("end_date must not precede start_date")

    calls = int(max_calls)
    if not 1 <= calls <= MAX_DISCOVERY_CALLS:
        raise ValueError(f"max_discovery_calls must be between 1 and {MAX_DISCOVERY_CALLS}")

    total_days = (end - start).days + 1
    selected_count = min(total_days, calls)
    if selected_count == 1:
        return (start,)
    if selected_count == total_days:
        return tuple(start + timedelta(days=offset) for offset in range(total_days))

    # Evenly spaced integer offsets, inclusive of both ends. Since
    # selected_count <= total_days, the rounded positions are unique after the
    # small defensive de-duplication below.
    offsets = [
        round(index * (total_days - 1) / (selected_count - 1))
        for index in range(selected_count)
    ]
    unique_offsets = sorted(set(offsets))

    # Defensive fill for unusual rounding edge cases.
    if len(unique_offsets) < selected_count:
        for offset in range(total_days):
            if offset not in unique_offsets:
                unique_offsets.append(offset)
                if len(unique_offsets) == selected_count:
                    break
        unique_offsets.sort()

    return tuple(start + timedelta(days=offset) for offset in unique_offsets[:selected_count])


@dataclass(frozen=True)
class SampleRequestPlan:
    schema_version: str
    sport_key: str
    start_date: str
    end_date: str
    date_range_days: int
    sample_events: int
    horizons_hours: tuple[float, ...]
    markets: tuple[str, ...]
    bookmakers: tuple[str, ...]
    max_discovery_calls: int
    max_odds_credits: int
    discovery_strategy: str
    discovery_dates: tuple[str, ...]
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
        value["discovery_dates"] = list(self.discovery_dates)
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
    if not 1 <= int(sample_events) <= MAX_SAMPLE_EVENTS:
        raise ValueError(f"sample_events must be between 1 and {MAX_SAMPLE_EVENTS}")
    if not 1 <= int(max_discovery_calls) <= MAX_DISCOVERY_CALLS:
        raise ValueError(f"max_discovery_calls must be between 1 and {MAX_DISCOVERY_CALLS}")
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

    discovery_schedule = select_discovery_dates(start, end, int(max_discovery_calls))
    discovery_dates = tuple(value.isoformat() for value in discovery_schedule)

    # One request per event and horizon, plus one closing snapshot per event.
    snapshot_upper = int(sample_events) * (len(normalized_horizons) + 1)
    identity = {
        "schema_version": "1.1",
        "sport_key": sport_key,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "date_range_days": int((end - start).days + 1),
        "sample_events": int(sample_events),
        "horizons_hours": list(normalized_horizons),
        "markets": list(normalized_markets),
        "bookmakers": list(normalized_bookmakers),
        "max_discovery_calls": int(max_discovery_calls),
        "max_odds_credits": int(max_odds_credits),
        "discovery_strategy": "all_days" if len(discovery_dates) == (end - start).days + 1 else "evenly_spaced",
        "discovery_dates": list(discovery_dates),
        "estimated_discovery_calls": len(discovery_dates),
        "estimated_snapshot_requests_upper_bound": snapshot_upper,
        "estimated_credits_upper_bound": int(max_odds_credits),
    }
    plan_request_id = "REQ-" + hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()[:24].upper()
    return SampleRequestPlan(
        schema_version=identity["schema_version"],
        sport_key=identity["sport_key"],
        start_date=identity["start_date"],
        end_date=identity["end_date"],
        date_range_days=identity["date_range_days"],
        sample_events=identity["sample_events"],
        horizons_hours=normalized_horizons,
        markets=normalized_markets,
        bookmakers=normalized_bookmakers,
        max_discovery_calls=identity["max_discovery_calls"],
        max_odds_credits=identity["max_odds_credits"],
        discovery_strategy=identity["discovery_strategy"],
        discovery_dates=discovery_dates,
        estimated_discovery_calls=identity["estimated_discovery_calls"],
        estimated_snapshot_requests_upper_bound=identity["estimated_snapshot_requests_upper_bound"],
        estimated_credits_upper_bound=identity["estimated_credits_upper_bound"],
        plan_request_id=plan_request_id,
    )


def validate_plan_request_id(plan: SampleRequestPlan, supplied: str) -> None:
    if not supplied or supplied.strip() != plan.plan_request_id:
        raise ValueError("plan_request_id does not match the immutable zero-credit estimate")
