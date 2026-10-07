"""Timestamp-aligned event reactions. Association is not causal attribution."""

from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from src.data_sources.calendar_models import CalendarEvent


class MarketEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    event_id: str
    name: str
    timestamp: AwareDatetime
    currency: str
    source: str
    actual: float | None = None
    consensus: float | None = None
    unit: str = ""

    @classmethod
    def from_calendar(cls, event: CalendarEvent, *, source: str, unit: str = "") -> "MarketEvent":
        """Bridge the existing macro calendar without discarding zero or unknown values."""
        return cls(
            event_id=event.event_id,
            name=event.name,
            timestamp=event.datetime_utc,
            currency=event.ccy,
            source=source,
            unit=unit,
            actual=event.actual,
            consensus=event.forecast,
        )


class AssetInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["price", "yield_percent", "vol_index"] = "price"
    source: str
    currency: str


def load_events_csv(path: str | Path) -> list[MarketEvent]:
    raw = pd.read_csv(path).astype(object)
    raw = raw.where(pd.notna(raw), None)
    events = [MarketEvent.model_validate(row) for row in raw.to_dict("records")]
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("Duplicate event_id")
    return sorted(events, key=lambda event: event.timestamp)


class EventStudyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    volatility_window: int = Field(default=20, ge=2)
    daily_staleness_days: int = Field(default=4, ge=1)
    intraday_window_minutes: int = Field(default=60, ge=1)
    intraday_tolerance_minutes: int = Field(default=5, ge=1)


def _move(before: float, after: float, kind: str) -> float:
    if kind == "yield_percent":
        return (after - before) * 100  # 4.20% to 4.25% = +5 bp
    if kind == "vol_index":
        return after - before
    if before <= 0 or after <= 0:
        raise ValueError("Price levels must be positive")
    return after / before - 1


def event_reaction(
    series: pd.Series,
    event: MarketEvent,
    asset: AssetInfo,
    as_of: pd.Timestamp,
    config: EventStudyConfig | None = None,
    intraday: pd.Series | None = None,
) -> dict:
    config = config or EventStudyConfig()
    if as_of.tzinfo is None:
        raise ValueError("as_of must include timezone")
    if (
        not isinstance(series.index, pd.DatetimeIndex)
        or series.index.tz is None
        or not series.index.is_unique
        or not series.index.is_monotonic_increasing
        or not np.isfinite(series).all()
    ):
        raise ValueError("Finite chronological timezone-aware observations required")
    if asset.kind == "price" and (series <= 0).any():
        raise ValueError("Prices must be positive")
    if not series.index.normalize().is_unique:
        raise ValueError("Daily input must contain at most one close per UTC day")
    t = pd.Timestamp(event.timestamp)
    observed = series.loc[series.index <= as_of]
    before, after = observed.loc[observed.index < t], observed.loc[observed.index >= t]
    result = {
        "event_id": event.event_id,
        "catalyst": event.name,
        "event_time": t.isoformat(),
        "source": event.source,
        "market_source": asset.source,
        "move_unit": {"price": "return_decimal", "yield_percent": "bp", "vol_index": "points"}[
            asset.kind
        ],
        "surprise": event.actual - event.consensus
        if t <= as_of and event.actual is not None and event.consensus is not None
        else None,
        "surprise_unit": event.unit,
        "pre_1_session": None,
        "post_1_close": None,
        "post_5_closes": None,
        "pre_timestamp": None,
        "post_1_timestamp": None,
        "post_5_timestamp": None,
        "vol_before": None,
        "vol_after": None,
        "vol_change": None,
        "intraday": None,
        "status": "upcoming" if t > as_of else "missing_pre_close",
    }
    if t > as_of or before.empty:
        return result
    if t - before.index[-1] > pd.Timedelta(days=config.daily_staleness_days):
        result["status"] = "stale_pre_close"
        return result
    result["status"] = "partial"
    result["pre_timestamp"] = before.index[-1].isoformat()
    if len(before) >= 2:
        result["pre_1_session"] = _move(before.iloc[-2], before.iloc[-1], asset.kind)
    if not after.empty and after.index[0] - t <= pd.Timedelta(days=config.daily_staleness_days):
        for horizon, key in [(1, "post_1_close"), (5, "post_5_closes")]:
            if len(after) >= horizon:
                result[key] = _move(before.iloc[-1], after.iloc[horizon - 1], asset.kind)
                result[f"post_{horizon}_timestamp"] = after.index[horizon - 1].isoformat()
        if len(after) >= 5:
            result["status"] = "observed"
        n = config.volatility_window
        # Yield/vol-index variability is daily change std, NOT price-return volatility.
        changes = (
            observed.pct_change(fill_method=None)
            if asset.kind == "price"
            else observed.diff() * (100 if asset.kind == "yield_percent" else 1)
        )
        pre_changes = changes.loc[changes.index < t].dropna().tail(n)
        post_changes = changes.loc[changes.index >= t].dropna().head(n)
        factor = np.sqrt(252) if asset.kind == "price" else 1
        if len(pre_changes) == n:
            result["vol_before"] = float(pre_changes.std(ddof=1) * factor)
        if len(post_changes) == n:
            result["vol_after"] = float(post_changes.std(ddof=1) * factor)
        if result["vol_before"] is not None and result["vol_after"] is not None:
            result["vol_change"] = result["vol_after"] - result["vol_before"]
    if intraday is not None:
        if (
            intraday.index.tz is None
            or not intraday.index.is_unique
            or not intraday.index.is_monotonic_increasing
            or not np.isfinite(intraday).all()
        ):
            raise ValueError("Invalid intraday timestamps or values")
        ticks = intraday.loc[intraday.index <= as_of]
        pre = ticks.loc[ticks.index < t]
        target = t + pd.Timedelta(minutes=config.intraday_window_minutes)
        post = ticks.loc[ticks.index >= target]
        tolerance = pd.Timedelta(minutes=config.intraday_tolerance_minutes)
        if (
            len(pre)
            and len(post)
            and t - pre.index[-1] <= tolerance
            and post.index[0] - target <= tolerance
        ):
            result["intraday"] = _move(pre.iloc[-1], post.iloc[0], asset.kind)
    return result


def similar_event_history(
    reactions: pd.DataFrame, catalyst: str, before: pd.Timestamp
) -> pd.DataFrame:
    """Only past events with fully observed 5-close windows at the query timestamp."""
    dates = pd.to_datetime(reactions["event_time"], utc=True)
    end = pd.to_datetime(reactions["post_5_timestamp"], utc=True)
    eligible = reactions.loc[
        (reactions["catalyst"] == catalyst) & (dates < before) & (end < before)
    ]
    return eligible.groupby(["asset", "move_unit"])[["post_1_close", "post_5_closes"]].agg(
        ["count", "mean", "median"]
    )
