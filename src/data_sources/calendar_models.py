from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict


class CalendarEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    datetime_utc: str  # ISO string "2026-01-27T13:30:00Z"
    country: str
    ccy: str
    name: str
    importance: int = Field(..., ge=1, le=5)

    forecast: float | None = None
    previous: float | None = None
    actual: float | None = None


class CalendarFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[CalendarEvent]
