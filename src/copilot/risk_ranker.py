from __future__ import annotations

from datetime import datetime, timezone

from src.data_sources.calendar_models import CalendarEvent


def _parse_utc(dt: str) -> datetime:
    return datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(timezone.utc)


def event_risk_score(
    event: CalendarEvent,
    net_expo_by_ccy: dict[str, float],
    *,
    horizon_hours: int = 72,
) -> float:
    """
    Simple score = importance * proximity * exposure
    - importance: 1..5 (already in model)
    - proximity: closer events score higher (0..1)
    - exposure: abs(net exposure) scaled
    """
    now = datetime.now(timezone.utc)
    t = _parse_utc(event.datetime_utc)
    dt_hours = (t - now).total_seconds() / 3600.0

    # only future events
    if dt_hours < 0 or dt_hours > horizon_hours:
        return 0.0

    proximity = max(0.0, 1.0 - dt_hours / horizon_hours)  # 1 now, 0 at horizon
    expo = abs(float(net_expo_by_ccy.get(event.ccy.upper(), 0.0)))

    # scale expo to "units" (50k exposure ~ 1 unit)
    expo_unit = expo / 50000.0

    return float(event.importance) * proximity * expo_unit


def top_calendar_risks(
    events: list[CalendarEvent],
    net_expo_by_ccy: dict[str, float],
    top_k: int = 5,
) -> list[dict]:
    scored = []
    for e in events:
        s = event_risk_score(e, net_expo_by_ccy)
        if s > 0:
            scored.append((s, e))

    scored.sort(key=lambda x: x[0], reverse=True)

    out = []
    for s, e in scored[:top_k]:
        out.append(
            {
                "event_id": e.event_id,
                "datetime_utc": e.datetime_utc,
                "ccy": e.ccy,
                "name": e.name,
                "importance": e.importance,
                "net_exposure_usd": float(net_expo_by_ccy.get(e.ccy.upper(), 0.0)),
                "score": round(float(s), 4),
            }
        )
    return out
