install:
	pip install -e .

snapshot:
	python -m scripts.train_snapshot

data:
	python -m scripts.download_real_data

train:
	python -m scripts.train_real

app:
	uvicorn webapp:app --reload

test:
	pytest -q

coverage:
	coverage run -m pytest -q && coverage report -m

backtest:
	python -m scripts.backtest_real

historical-plan:
	@echo "Use: python -m scripts.plan_historical_backfill --events-csv <csv> --max-credits <cap>"

historical-run:
	@echo "Use: python -m scripts.run_historical_backfill --plan-dir data/odds_api/backfill --max-credits <cap> --execute"

benchmark:
	@echo "Use: python -m scripts.run_market_benchmark --input <evaluation.csv> --persist"
