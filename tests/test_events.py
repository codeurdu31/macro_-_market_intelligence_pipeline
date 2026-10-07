import pandas as pd
import pytest

from src.analytics.events import (
    AssetInfo,
    EventStudyConfig,
    MarketEvent,
    event_reaction,
    similar_event_history,
)
from src.data_sources.calendar_models import CalendarEvent


def event(timestamp="2024-01-03T13:30:00Z", actual=0.0, consensus=0.1):
    return MarketEvent(
        event_id="CPI_1",
        name="US CPI",
        timestamp=timestamp,
        currency="USD",
        source="test",
        actual=actual,
        consensus=consensus,
    )


def daily():
    idx = pd.bdate_range("2024-01-01", periods=10, tz="UTC") + pd.Timedelta(hours=22)
    return pd.Series([100, 100, 98, 99, 100, 101, 102, 103, 104, 105], index=idx)


def test_existing_calendar_bridge():
    old = CalendarEvent(
        event_id="CPI",
        name="US CPI",
        datetime_utc="2024-01-03T13:30:00Z",
        country="US",
        ccy="USD",
        importance=5,
        forecast=0.0,
    )
    new = MarketEvent.from_calendar(old, source="manual")
    assert new.consensus == 0.0 and new.actual is None


def test_event_alignment_and_no_future_data():
    series = daily()
    asset = AssetInfo(source="test", currency="USD")
    result = event_reaction(series, event(), asset, series.index[4])
    assert result["post_1_close"] == pytest.approx(-0.02)
    assert result["post_5_closes"] is None
    assert result["surprise"] == pytest.approx(-0.1)  # zero is an actual value
    assert result["intraday"] is None
    result = event_reaction(series, event(), asset, series.index[-1])
    assert result["post_5_closes"] == pytest.approx(0.02)
    assert result["pre_timestamp"] == series.index[1].isoformat()


def test_after_close_and_upcoming():
    series = daily()
    asset = AssetInfo(source="test", currency="USD")
    result = event_reaction(series, event("2024-01-03T23:00Z"), asset, series.index[-1])
    assert result["post_1_close"] == pytest.approx(99 / 98 - 1)
    future = event_reaction(series, event(), asset, series.index[0])
    assert future["status"] == "upcoming" and future["surprise"] is None


def test_yield_units_and_missing_consensus():
    series = daily() * 0 + 4.0
    series.iloc[2:] = 4.05
    result = event_reaction(
        series,
        event(consensus=None),
        AssetInfo(kind="yield_percent", source="test", currency="USD"),
        series.index[-1],
    )
    assert result["post_1_close"] == pytest.approx(5)
    assert result["move_unit"] == "bp"
    assert result["surprise"] is None


def test_intraday_window_and_stale_quotes():
    series = daily()
    asset = AssetInfo(source="test", currency="USD")
    ticks = pd.Series([100, 98], index=pd.to_datetime(["2024-01-03T13:29Z", "2024-01-03T14:30Z"]))
    result = event_reaction(series, event(), asset, series.index[-1], intraday=ticks)
    assert result["intraday"] == pytest.approx(-0.02)
    ticks.index = pd.to_datetime(["2024-01-03T12:00Z", "2024-01-03T14:30Z"])
    assert (
        event_reaction(series, event(), asset, series.index[-1], intraday=ticks)["intraday"] is None
    )


def test_volatility_windows_and_similar_history():
    series = daily()
    row = event_reaction(
        series,
        event("2024-01-05T13:30Z"),
        AssetInfo(source="test", currency="USD"),
        series.index[-1],
        EventStudyConfig(volatility_window=2),
    )
    assert row["vol_before"] is not None and row["vol_after"] is not None
    frame = pd.DataFrame([{**row, "asset": "SPX"}])
    assert similar_event_history(frame, "US CPI", pd.Timestamp("2024-01-05T13:30Z")).empty
    summary = similar_event_history(frame, "US CPI", pd.Timestamp("2024-02-01T13:30Z"))
    assert summary[("post_1_close", "count")].iloc[0] == 1
