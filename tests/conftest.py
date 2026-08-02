from __future__ import annotations

import os
from pathlib import Path


TEST_DB = Path(f"/tmp/sports_prediction_v3_1_pytest_{os.getpid()}.db")
TEST_DB.unlink(missing_ok=True)
os.environ["APP_DATABASE_PATH"] = str(TEST_DB)
os.environ["APP_AUTH_REQUIRED"] = "false"
os.environ["APP_ENV"] = "test"


def pytest_sessionfinish(session, exitstatus):
    TEST_DB.unlink(missing_ok=True)
