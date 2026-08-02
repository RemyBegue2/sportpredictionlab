from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import pandas as pd
from sports_predictor.backtest import backtest_football, backtest_tennis

p=argparse.ArgumentParser()
p.add_argument('--football',default='data/processed/football_real.csv')
p.add_argument('--tennis',default='data/processed/tennis_real.csv')
p.add_argument('--output',default='artifacts/backtest_real.json')
p.add_argument('--football-initial',type=int,default=1200)
p.add_argument('--football-horizon',type=int,default=250)
p.add_argument('--tennis-initial',type=int,default=6000)
p.add_argument('--tennis-horizon',type=int,default=750)
p.add_argument('--folds',type=int,default=5)
a=p.parse_args()
f=pd.read_csv(a.football); t=pd.read_csv(a.tennis)
report={
 'football':backtest_football(f,initial_train=a.football_initial,horizon=a.football_horizon,max_folds=a.folds),
 'tennis':backtest_tennis(t,initial_train=a.tennis_initial,horizon=a.tennis_horizon,max_folds=a.folds),
 'interpretation':'A negative log-loss delta means the model beats the stated naive baseline. The 95% block-bootstrap interval should remain below zero before promotion.'
}
out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(report,indent=2))
