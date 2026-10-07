from __future__ import annotations

from datetime import date
import hashlib
import httpx

from src.core.config import get_env
from src.data_sources.calendar_models import CalendarEvent

EODHD_URL = "https://eodhd.com/api/economic-events"

# Map ISO2 country -> currency (fallback)
ISO2_TO_CCY = {
    "US": "USD",
    "GB": "GBP",
    "JP": "JPY",
    "CH": "CHF",
    "CA": "CAD",
    "AU": "AUD",
    "NZ": "NZD",
    # EUR bloc (subset)
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "NL": "EUR",
    "BE": "EUR",
    "AT": "EUR",
    "PT": "EUR",
    "IE": "EUR",
    "FI": "EUR",
    "GR": "EUR",
}


def _impact_to_importance5(x: str | None) -> int:
    if not x:
        return 3
    s = x.strip().lower()
    if "high" in s:
        return 5
    if "medium" in s:
        return 3
    if "low" in s:
        return 2
    return 3


def _to_iso_utc(dt: str | None) -> str:
    """
    Make a best-effort UTC ISO string.
    EODHD usually returns a datetime-like string. If only date, we set 00:00Z.
    """
    if not dt:
        return "1970-01-01T00:00:00Z"
    t = dt.strip()
    if "T" in t:
        return t if t.endswith("Z") else t + "Z"
    return t + "T00:00:00Z"


def _infer_ccy(item: dict) -> str:
    ccy = (item.get("currency") or item.get("Currency") or "").strip().upper()
    if len(ccy) == 3 and ccy.isalpha():
        return ccy
    iso2 = (item.get("country") or item.get("Country") or "").strip().upper()
    return ISO2_TO_CCY.get(iso2, "UNK")


def fetch_eodhd_calendar(
    start: date,
    end: date,
    countries_iso2: list[str] | None = None,
    limit: int = 200,
) -> list[CalendarEvent]:
    """
    EODHD doc:
    https://eodhd.com/api/economic-events?api_token=demo&fmt=json
    Supports from/to (YYYY-MM-DD) and country ISO2. :contentReference[oaicite:2]{index=2}
    """
    token = get_env("EODHD_API_TOKEN")

    base_params = {
        "api_token": token,
        "fmt": "json",
        "from": start.isoformat(),  # from/to parameters supported :contentReference[oaicite:3]{index=3}
        "to": end.isoformat(),
        "limit": str(limit),
    }

    items: list[dict] = []

    if countries_iso2:
        for c in countries_iso2:
            params = dict(base_params)
            params["country"] = c  # ISO2 country supported :contentReference[oaicite:4]{index=4}
            r = httpx.get(EODHD_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                items.extend(data)
    else:
        r = httpx.get(EODHD_URL, params=base_params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            items = data

    out: list[CalendarEvent] = []

    for it in items:
        dt_raw = it.get("date") or it.get("Date") or it.get("datetime") or it.get("Datetime")
        name = it.get("event") or it.get("Event") or it.get("type") or it.get("Type") or "Unknown"
        country = it.get("country") or it.get("Country") or ""
        impact = it.get("impact") or it.get("Impact")

        actual = it.get("actual") or it.get("Actual")
        forecast = it.get("forecast") or it.get("Forecast") or it.get("estimate") or it.get("Estimate")
        previous = it.get("previous") or it.get("Previous")

        # stable event_id
        raw_id = f"{dt_raw}|{country}|{name}"
        event_id = "EODHD_" + hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:12]

        out.append(
            CalendarEvent(
                event_id=event_id,
                datetime_utc=_to_iso_utc(str(dt_raw) if dt_raw is not None else None),
                country=str(country),
                ccy=_infer_ccy(it),
                name=str(name),
                importance=_impact_to_importance5(str(impact) if impact is not None else None),
                actual=actual,
                forecast=forecast,
                previous=previous,
            )
        )

    # simple sort
    out.sort(key=lambda e: e.datetime_utc)
    return out
