from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.cloud_config import CloudSettings
from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig
from sports_predictor.database import (
    init_database,
    persist_event_result,
    record_data_quality_issue,
    settle_shadow_predictions,
)
from sports_predictor.odds_data import normalize_scores_payload


def sync_results(*, sports: list[str], days_from: int | None = 3, client: OddsApiClient | None = None, event_ids_by_sport: dict[str, list[str]] | None = None) -> dict[str, Any]:
    provider = client or OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    imported = 0
    completed_seen = 0
    quota_remaining: int | None = None
    skipped_sports = 0
    for sport in sports:
        event_ids = (event_ids_by_sport or {}).get(sport) if event_ids_by_sport is not None else None
        if event_ids_by_sport is not None and not event_ids:
            skipped_sports += 1
            continue
        response = provider.scores(sport, days_from=days_from, event_ids=event_ids)
        quota_remaining = response.quota.remaining if response.quota.remaining is not None else quota_remaining
        rows = normalize_scores_payload(response.payload)
        completed = rows[rows["completed"] & rows["home_score"].notna() & rows["away_score"].notna()]
        completed_seen += len(completed)
        for row in completed.to_dict(orient="records"):
            try:
                persist_event_result(
                    provider_event_id=str(row["event_id"]),
                    home_score=int(row["home_score"]),
                    away_score=int(row["away_score"]),
                    completed_at=row.get("last_update") or row["commence_time"],
                )
                imported += 1
            except ValueError as exc:
                record_data_quality_issue(
                    issue_type="score_without_known_event",
                    severity="warning",
                    provider_event_id=str(row.get("event_id") or "") or None,
                    details={"sport_key": sport, "reason": str(exc)},
                )
        print(f"{sport}: completed={len(completed)} imported={imported} quota_remaining={response.quota.remaining}")
    settlement = settle_shadow_predictions()
    return {
        "completed_seen": completed_seen,
        "imported": imported,
        "shadow_settled": int(settlement.get("settled", 0)),
        "shadow_skipped": int(settlement.get("skipped", 0)),
        "quota_remaining": quota_remaining,
        "skipped_sports": skipped_sports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync completed results from the provider's recent scores window.")
    parser.add_argument("--sports", nargs="+", default=None)
    parser.add_argument("--days-from", type=int, default=3)
    args = parser.parse_args()
    settings = CloudSettings.from_env(ROOT)
    init_database(settings)
    sports = args.sports or list(settings.odds_sync_sports)
    summary = sync_results(sports=list(sports), days_from=args.days_from)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
