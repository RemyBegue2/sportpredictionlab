from __future__ import annotations

from scripts.sync_current_odds import main as sync_odds
from scripts.sync_recent_results import main as sync_results


def main() -> int:
    odds_status = sync_odds()
    if odds_status != 0:
        return int(odds_status)
    return int(sync_results())


if __name__ == "__main__":
    raise SystemExit(main())
