from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_sources.calendar_models import CalendarEvent, CalendarFile


def _parse_utc(dt: str) -> datetime:
    # "2026-01-27T13:30:00Z" -> aware UTC
    return datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_manual_calendar(path: str = "data/calendar_manual.json") -> list[CalendarEvent]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return CalendarFile.model_validate(raw).events
    return [CalendarEvent.model_validate(x) for x in raw]


def filter_window(events: list[CalendarEvent], start_utc: datetime, end_utc: datetime) -> list[CalendarEvent]:
    out: list[CalendarEvent] = []
    for e in events:
        t = _parse_utc(e.datetime_utc)
        if start_utc <= t <= end_utc:
            out.append(e)
    out.sort(key=lambda x: x.datetime_utc)
    return out
