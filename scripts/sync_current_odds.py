from __future__ import annotations

import argparse
import json
from typing import Any

from sports_predictor.data_sources.the_odds_api import OddsApiError, OddsApiNotConfigured
from webapp import SETTINGS, SPORT_LEAGUE_MAP, _football_odds_slate, _tennis_odds_slate, odds_client


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Persist current pre-match odds and audit predictions.")
    p.add_argument("--football", action="append", dest="football_sports", help="The Odds API football sport key. Repeatable.")
    p.add_argument("--include-tennis", action="store_true", help="Also discover active tennis tournaments. Disabled by default to protect quota.")
    p.add_argument("--tennis-surface", default="hard", choices=("hard", "clay", "grass", "carpet"))
    p.add_argument("--max-tennis-tournaments", type=int, default=4)
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
    football_sports = tuple(args.football_sports or SETTINGS.odds_sync_sports)
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
