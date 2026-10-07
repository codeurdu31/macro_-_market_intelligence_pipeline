from __future__ import annotations

from datetime import datetime, timezone, timedelta

from src.data_sources.event_window import event_stage
from src.data_sources.calendar_manual import load_manual_calendar, filter_window


def main() -> None:
    now = datetime.now(timezone.utc)
    today = now.date()
    end = today + timedelta(days=3)

    start_dt = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)

    events_all = load_manual_calendar("data/calendar_manual.json")
    events = filter_window(events_all, start_dt, end_dt)

    print(f"✅ Window: {today} -> {end}")
    print(f"✅ Manual events fetched: {len(events)}")

    for e in events[:50]:
        stage = event_stage(e.datetime_utc)
        print(f"- [{e.ccy}] {e.name} | imp={e.importance} | {stage} | {e.datetime_utc} | {e.country}")


if __name__ == "__main__":
    main()
