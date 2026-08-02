from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig
from sports_predictor.odds_backtest import build_historical_plan
from sports_predictor.odds_data import normalize_odds_payload


DEFAULT_BOOKMAKERS = ["winamax_fr", "betclic_fr", "unibet_fr", "pmu_fr", "netbet_fr", "pinnacle"]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Planifie puis télécharge des snapshots historiques The Odds API.")
    p.add_argument("--events-csv", required=True, help="CSV avec sport_key,event_id,commence_time")
    p.add_argument("--horizons-hours", nargs="+", type=float, default=[24, 6, 1])
    p.add_argument("--closing-minutes", type=int, default=10)
    p.add_argument("--markets", nargs="+", default=["h2h"])
    p.add_argument("--bookmakers", nargs="+", default=DEFAULT_BOOKMAKERS)
    p.add_argument("--max-credits", type=int, default=5000)
    p.add_argument("--output-dir", default="data/odds_api/historical")
    p.add_argument("--execute", action="store_true", help="Sans ce drapeau, le script reste en dry-run.")
    p.add_argument("--force-refresh", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    events = pd.read_csv(args.events_csv)
    plan = build_historical_plan(
        events,
        horizons_hours=args.horizons_hours,
        closing_minutes=args.closing_minutes,
        markets=args.markets,
        bookmakers=args.bookmakers,
    )
    output = ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    plan.requests.to_csv(output / "request_plan.csv", index=False)
    plan.targets.to_csv(output / "event_targets.csv", index=False)
    summary = {
        "request_count": len(plan.requests),
        "target_count": len(plan.targets),
        "estimated_credits": plan.estimated_credits,
        "markets": list(plan.markets),
        "bookmakers": list(plan.bookmakers),
        "execution_requested": bool(args.execute),
    }
    (output / "plan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if plan.estimated_credits > args.max_credits:
        print(f"ABORT: estimation {plan.estimated_credits} > plafond {args.max_credits} crédits")
        return 3
    if not args.execute:
        print("DRY-RUN terminé. Relancez avec --execute après vérification du budget.")
        return 0

    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    all_rows: list[pd.DataFrame] = []
    for row in plan.requests.to_dict(orient="records"):
        snapshot = pd.Timestamp(row["snapshot_at"]).isoformat().replace("+00:00", "Z")
        response = client.historical_odds(
            str(row["sport_key"]),
            snapshot_at=snapshot,
            markets=plan.markets,
            bookmakers=plan.bookmakers,
            force_refresh=args.force_refresh,
        )
        normalized = normalize_odds_payload(response.payload)
        if not normalized.empty:
            normalized["requested_snapshot_at"] = snapshot
            normalized["request_fingerprint"] = response.request_fingerprint
            all_rows.append(normalized)
        print(f"{row['request_number']}/{len(plan.requests)} {row['sport_key']} {snapshot} · remaining={response.quota.remaining}")
    combined = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    combined.to_csv(output / "historical_odds_long.csv", index=False)
    print(f"Écrit: {output / 'historical_odds_long.csv'} ({len(combined)} lignes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
