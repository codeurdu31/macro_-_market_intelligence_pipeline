"""Strict CSV contracts; no implicit filling or invented market observations."""

import csv
from pathlib import Path

import numpy as np
import pandas as pd


def validate_panel(frame: pd.DataFrame, *, positive: bool = True) -> pd.DataFrame:
    """Require aligned UTC observations. Missing prices must be resolved upstream."""
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("A timezone-aware DatetimeIndex is required")
    if frame.empty or not len(frame.columns) or frame.columns.has_duplicates:
        raise ValueError("An unambiguous, nonempty panel is required")
    if frame.index.hasnans or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Timestamps must be valid, unique and increasing")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (positive and (values <= 0).any()):
        raise ValueError("Observations must be finite and prices strictly positive")
    result = frame.astype(float).copy()
    result.index = result.index.tz_convert("UTC")
    return result


def load_market_csv(path: str | Path, *, positive: bool = True) -> pd.DataFrame:
    """Wide CSV: timestamp,ASSET1,ASSET2. Timestamps need explicit UTC offsets."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), [])
    if len(header) != len(set(header)):
        raise ValueError("Duplicate CSV columns")
    raw = pd.read_csv(path)
    if "timestamp" not in raw:
        raise ValueError("Missing timestamp column")
    timestamps = [pd.Timestamp(value) for value in raw.pop("timestamp")]
    if any(t.tzinfo is None for t in timestamps):
        raise ValueError("CSV timestamps must include a timezone")
    raw.index = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True))
    return validate_panel(raw, positive=positive)
