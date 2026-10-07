from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
import httpx

from src.core.config import get_env
from src.data_sources.calendar_models import CalendarEvent

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


def _to_iso_utc(x: str | None) -> str:
    if not x:
        return "1970-01-01T00:00:00Z"
    s = str(x).strip()
    # FMP renvoie souvent un champ date "YYYY-MM-DD" ou datetime.
    if "T" in s and s.endswith("Z"):
        return s
    if " " in s and "T" not in s:
        return s.replace(" ", "T") + "Z"
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s + "T00:00:00Z"
    return s if s.endswith("Z") else s + "Z"


def _impact_to_importance5(x: str | None) -> int:
    if not x:
        return 3
    t = str(x).strip().lower()
    if "high" in t:
        return 5
    if "medium" in t:
        return 3
    if "low" in t:
        return 2
    return 3


def fetch_fmp_economic_calendar(
    start: date,
    end: date,
    *,
    filter_currencies: list[str] | None = None,
) -> list[CalendarEvent]:
    """
    Endpoint doc:
    https://financialmodelingprep.com/stable/economic-calendar :contentReference[oaicite:3]{index=3}
    Auth: apikey=... (FMP key from dashboard) :contentReference[oaicite:4]{index=4}
    """
    api_key = get_env("FMP_API_KEY")
    url = f"{FMP_BASE_URL}/economic-calendar"

    # Beaucoup d'endpoints FMP acceptent from/to. Si ce n'est pas le cas, on filtre localement.
    params = {
        "apikey": api_key,
        "from": start.isoformat(),
        "to": end.isoformat(),
    }

    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    items = r.json() or []
    if not isinstance(items, list):
        items = []

    # bornes locales, au cas où l'API renvoie plus large
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)

    out: list[CalendarEvent] = []

    for it in items:
        # champs typiques (on met des fallbacks, car FMP peut varier selon route/stable)
        dt_raw = it.get("date") or it.get("datetime") or it.get("time")
        dt_utc = _to_iso_utc(dt_raw)

        try:
            dtp = datetime.fromisoformat(dt_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue

        if not (start_dt <= dtp <= end_dt):
            continue

        country = str(it.get("country") or "")
        name = str(it.get("event") or it.get("name") or it.get("indicator") or "Unknown")
        ccy = (str(it.get("currency") or it.get("ccy") or "UNK")).strip().upper()

        if filter_currencies and ccy not in set(filter_currencies):
            continue

        raw_id = f"{dt_utc}|{country}|{ccy}|{name}"
        event_id = "FMP_" + hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:12]

        out.append(
            CalendarEvent(
                event_id=event_id,
                datetime_utc=dt_utc,
                country=country,
                ccy=ccy,
                name=name,
                importance=_impact_to_importance5(it.get("impact")),
                actual=it.get("actual"),
                forecast=it.get("estimate") or it.get("forecast"),
                previous=it.get("previous"),
            )
        )

    out.sort(key=lambda e: e.datetime_utc)
    return out
