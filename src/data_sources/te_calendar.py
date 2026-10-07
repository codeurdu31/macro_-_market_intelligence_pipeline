from __future__ import annotations

from datetime import date
import httpx

from src.core.config import get_env
from src.data_sources.calendar_models import CalendarEvent

TE_BASE_URL = "https://api.tradingeconomics.com"


def _importance_te_to_5(x: int) -> int:
    return {1: 2, 2: 3, 3: 5}.get(x, 3)


def fetch_te_calendar_all_by_date(
    start: date,
    end: date,
    importance: int | None = 2,          # TE: 1..3
    keep_countries: list[str] | None = None,
) -> list[CalendarEvent]:
    """
    Uses the documented endpoint:
    /calendar/country/All/{start}/{end}?importance={importance} :contentReference[oaicite:4]{index=4}
    Then filters locally by country to avoid 403 issues with guest keys.
    """
    api_key = get_env("TE_API_KEY")

    url = f"{TE_BASE_URL}/calendar/country/All/{start.isoformat()}/{end.isoformat()}"
    params = {"c": api_key, "f": "json"}
    if importance is not None:
        params["importance"] = str(int(importance))

    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    keep_set = None
    if keep_countries:
        keep_set = {c.strip().lower() for c in keep_countries}

    out: list[CalendarEvent] = []

    for it in data:
        country = str(it.get("Country") or "").strip()
        if keep_set is not None and country.lower() not in keep_set:
            continue

        imp = int(it.get("Importance") or 0)

        dt = str(it.get("Date") or "").strip()
        dt_utc = dt + "Z" if dt and not dt.endswith("Z") else dt

        out.append(
            CalendarEvent(
                event_id=f"TE_{it.get('CalendarId', it.get('Ticker', 'UNKNOWN'))}",
                datetime_utc=dt_utc,
                country=country,
                ccy=(str(it.get("Currency") or "").strip().upper() or "UNK"),
                name=str(it.get("Event") or it.get("Category") or "Unknown").strip(),
                importance=_importance_te_to_5(imp),
                actual=None,
                forecast=None,
                previous=None,
            )
        )

    return out
