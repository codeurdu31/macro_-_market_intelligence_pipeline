from __future__ import annotations

from datetime import datetime, timezone


def event_stage(datetime_utc: str, pre_min: int = 120, live_min: int = 15, post_min: int = 60) -> str:
    """
    Classifies event timing vs now (UTC).
    - PRE: within next 2h
    - LIVE: within +/- 15min
    - POST: within last 60min
    - FAR: otherwise
    """
    now = datetime.now(timezone.utc)
    dt = datetime.fromisoformat(datetime_utc.replace("Z", "+00:00"))

    delta_min = (dt - now).total_seconds() / 60.0

    if abs(delta_min) <= live_min:
        return "LIVE"
    if 0 < delta_min <= pre_min:
        return "PRE"
    if -post_min <= delta_min < 0:
        return "POST"
    return "FAR"
