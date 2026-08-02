from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.data_sources.the_odds_api import OddsApiClient, OddsApiConfig, OddsApiError


def main() -> int:
    client = OddsApiClient(OddsApiConfig.from_env(root=ROOT))
    if not client.config.configured:
        print("THE_ODDS_API_KEY absent. Définissez-la dans votre environnement, jamais dans le code.")
        return 2
    try:
        response = client.list_sports(force_refresh=True)
    except OddsApiError as exc:
        print(f"Connexion impossible: {exc}")
        return 1
    active = [x for x in response.payload if x.get("active")]
    tennis = [x for x in active if str(x.get("group", "")).lower() == "tennis"]
    soccer = [x for x in active if str(x.get("group", "")).lower() == "soccer"]
    print(f"Connexion OK. Sports actifs: {len(active)} · football: {len(soccer)} · tennis: {len(tennis)}")
    print(f"Quota: remaining={response.quota.remaining}, used={response.quota.used}, last={response.quota.last_cost}")
    for item in (soccer[:5] + tennis[:5]):
        print(f"- {item['key']}: {item['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
