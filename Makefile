install:
	pip install -e .

snapshot:
	python scripts/train_snapshot.py

data:
	python scripts/download_real_data.py

train:
	python scripts/train_real.py

app:
	uvicorn webapp:app --reload

test:
	pytest -q

backtest:
	python scripts/backtest_real.py
