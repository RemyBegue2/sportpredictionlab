from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_predictor.fresh_rebuild import SEASON_SOURCES, build_multiseason_dataset, download_season, rebuild_candidate


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Download, validate and train a fresh multi-season Premier League candidate.")
    p.add_argument("--download", action="store_true", help="Download the public season CSVs before training.")
    p.add_argument("--promote", action="store_true", help="Promote only when every chronological policy check passes.")
    p.add_argument("--raw-dir", default="data/real/epl_seasons")
    p.add_argument("--data-output", default="data/real/football_epl_2021_2026.csv")
    p.add_argument("--artifacts", default="artifacts")
    return p


def main() -> int:
    args = parser().parse_args()
    raw_dir = ROOT / args.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for season in SEASON_SOURCES:
        filename = f"epl_{season.replace('-', '_')}.csv"
        target = raw_dir / filename
        if args.download:
            download_season(season, target)
        if not target.exists():
            raise SystemExit(f"Missing {target}. Re-run with --download.")
        paths.append(target)
    dataset = build_multiseason_dataset(paths)
    report = rebuild_candidate(
        dataset=dataset,
        artifacts_dir=ROOT / args.artifacts,
        data_output=ROOT / args.data_output,
        promote=args.promote,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
