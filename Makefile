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

release-manifest:
	python -m scripts.generate_release_manifest

handoff:
	python -m scripts.generate_release_manifest
	python -m scripts.export_handoff

release-snapshot:
	python -m scripts.snapshot_release

system-proof:
	@echo "Use: python -m scripts.post_deploy_verify --base-url <url> --expected-version 3.5.0"

db-backup:
	python -m scripts.portable_db_backup --backup
