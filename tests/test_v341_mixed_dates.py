from __future__ import annotations

import pandas as pd

from sports_predictor.common import chronological_group_split_indices, validate_date_order


def test_validate_date_order_accepts_date_and_iso_timestamp_mix() -> None:
    frame = pd.DataFrame({
        "date": [
            "2026-08-02",
            "2026-08-03T18:30:00+00:00",
            "2026-08-04T00:00:00Z",
        ],
        "value": [1, 2, 3],
    })
    parsed = validate_date_order(frame)
    assert str(parsed["date"].dtype) == "datetime64[ns, UTC]"
    assert parsed["date"].is_monotonic_increasing


def test_group_split_accepts_mixed_iso_date_formats() -> None:
    dates = [
        *[f"2024-01-{day:02d}" for day in range(1, 13)],
        *[f"2024-02-{day:02d}T18:00:00+00:00" for day in range(1, 11)],
        *[f"2024-03-{day:02d}T20:00:00Z" for day in range(1, 11)],
    ]
    train, calibration, test = chronological_group_split_indices(dates)
    assert train.stop <= calibration.start
    assert calibration.stop <= test.start
    assert test.stop == len(dates)
