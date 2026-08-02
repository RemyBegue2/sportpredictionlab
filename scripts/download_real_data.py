from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from sports_predictor.data_sources import FootballDataSource, TennisArchiveSource

p=argparse.ArgumentParser()
p.add_argument("--football-seasons", nargs="*", default=["2021-22","2022-23","2023-24","2024-25","2025-26"])
p.add_argument("--football-leagues", nargs="*", default=["E0","F1","D1","I1","SP1"])
p.add_argument("--tennis-years", nargs="*", type=int, default=list(range(2019,2027)))
p.add_argument("--output", default="data/processed")
a=p.parse_args(); out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
football, fm=FootballDataSource().fetch_many(a.football_seasons,a.football_leagues)
tennis, tm=TennisArchiveSource().fetch_many(a.tennis_years)
football.to_csv(out/"football_real.csv",index=False); tennis.to_csv(out/"tennis_real.csv",index=False)
(out/"manifests.json").write_text(json.dumps([m.__dict__ for m in fm+tm],indent=2,ensure_ascii=False),encoding="utf-8")
print({"football_rows":len(football),"tennis_rows":len(tennis),"output":str(out)})
