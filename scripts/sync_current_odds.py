from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import Any

from sports_predictor.data_sources.the_odds_api import OddsApiError, OddsApiNotConfigured
from webapp import SETTINGS, SPORT_LEAGUE_MAP, _football_odds_slate, _tennis_odds_slate, odds_client


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Persist current pre-match odds and audit predictions.")
    p.add_argument("--football", action="append", dest="football_sports", help="The Odds API football sport key. Repeatable.")
    p.add_argument("--include-tennis", action="store_true", help="Also discover active tennis tournaments. Disabled by default to protect quota.")
    p.add_argument("--tennis-surface", default="hard", choices=("hard", "clay", "grass", "carpet"))
    p.add_argument("--max-tennis-tournaments", type=int, default=4)
    p.add_argument("--confirmation", default=None, help="Must equal EXECUTE_DAILY_ODDS for paid network calls")
    p.add_argument("--max-credits", type=int, default=None, help="Hard planning cap for this run")
    return p


def _safe_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "sport_key": payload.get("sport_key"),
        "events": payload.get("summary", {}).get("events", 0),
        "winamax_available": payload.get("summary", {}).get("winamax_available", 0),
        "research_candidates": payload.get("summary", {}).get("research_candidates", 0),
        "stored_snapshots": payload.get("storage", {}).get("inserted_snapshots", 0),
        "from_cache": payload.get("from_cache", False),
        "quota_remaining": payload.get("quota", {}).get("remaining"),
        "quota_last_cost": payload.get("quota", {}).get("last_cost"),
    }


def main() -> int:
    args = parser().parse_args()
    configured_cap = SETTINGS.daily_odds_max_credits
    requested_cap = configured_cap if args.max_credits is None else max(0, int(args.max_credits))
    effective_cap = min(configured_cap, requested_cap) if configured_cap else 0
    if not SETTINGS.daily_odds_enabled or effective_cap <= 0:
        print(json.dumps({
            "status": "skipped_credit_firewall",
            "reason": "daily paid odds are disabled",
            "credits_consumed": 0,
            "automatic_bet_placement": False,
        }, ensure_ascii=False))
        return 0
    confirmation = args.confirmation or __import__("os").getenv("DAILY_ODDS_CONFIRMATION")
    if confirmation != "EXECUTE_DAILY_ODDS":
        print(json.dumps({
            "status": "blocked_confirmation_required",
            "required_confirmation": "EXECUTE_DAILY_ODDS",
            "credits_consumed": 0,
        }, ensure_ascii=False))
        return 2
    football_sports = tuple(args.football_sports or SETTINGS.odds_sync_sports)
    estimated_calls = len(football_sports) + ((1 + max(0, args.max_tennis_tournaments)) if args.include_tennis else 0)
    if estimated_calls > effective_cap:
        print(json.dumps({
            "status": "blocked_credit_cap",
            "estimated_credits": estimated_calls,
            "maximum_credits": effective_cap,
            "credits_consumed": 0,
        }, ensure_ascii=False))
        return 2
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for sport_key in football_sports:
        league = SPORT_LEAGUE_MAP.get(sport_key)
        if not league:
            errors.append({"sport_key": sport_key, "error": "no bundled model mapping"})
            continue
        try:
            results.append(_safe_summary(_football_odds_slate(sport_key, league, force_refresh=True)))
        except Exception as exc:
            errors.append({"sport_key": sport_key, "error": type(exc).__name__})

    if args.include_tennis:
        try:
            sports = odds_client().list_sports(force_refresh=True).payload
            active = [x for x in sports if x.get("active") and str(x.get("group", "")).casefold() == "tennis"]
            for item in active[: max(0, args.max_tennis_tournaments)]:
                sport_key = str(item.get("key", ""))
                try:
                    results.append(_safe_summary(_tennis_odds_slate(sport_key, args.tennis_surface, force_refresh=True)))
                except Exception as exc:
                    errors.append({"sport_key": sport_key, "error": type(exc).__name__})
        except (OddsApiNotConfigured, OddsApiError) as exc:
            errors.append({"sport_key": "tennis_discovery", "error": type(exc).__name__})

    print(json.dumps({"status": "ok" if not errors else "partial_failure", "results": results, "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
