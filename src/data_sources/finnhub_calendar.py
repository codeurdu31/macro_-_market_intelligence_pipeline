from __future__ import annotations

import hashlib
from datetime import date
import httpx

from src.core.config import get_env
from src.data_sources.calendar_models import CalendarEvent

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _impact_to_importance5(x: str | None) -> int:
    if not x:
        return 3
    s = str(x).strip().lower()
    if "high" in s:
        return 5
    if "medium" in s:
        return 3
    if "low" in s:
        return 2
    return 3


def _to_iso_utc(s: str | None) -> str:
    """
    Finnhub renvoie souvent un champ 'time' style 'YYYY-MM-DD HH:MM:SS' (sans timezone).
    On le traite comme UTC et on convertit en ISO 'YYYY-MM-DDTHH:MM:SSZ'.
    """
    if not s:
        return "1970-01-01T00:00:00Z"
    t = str(s).strip()
    # déjà ISO ?
    if "T" in t and t.endswith("Z"):
        return t
    # "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DDTHH:MM:SSZ"
    if " " in t and "T" not in t:
        return t.replace(" ", "T") + "Z"
    # "YYYY-MM-DD" -> minuit UTC
    if len(t) == 10 and t[4] == "-" and t[7] == "-":
        return t + "T00:00:00Z"
    # fallback
    return t if t.endswith("Z") else t + "Z"


def fetch_finnhub_calendar(
    start: date,
    end: date,
    *,
    filter_currencies: list[str] | None = None,
) -> list[CalendarEvent]:
    """
    GET /calendar/economic?from=YYYY-MM-DD&to=YYYY-MM-DD&token=APIKEY
    Docs: /calendar/economic avec args from/to. :contentReference[oaicite:3]{index=3}
    Auth: token=apiKey ou header X-Finnhub-Token. :contentReference[oaicite:4]{index=4}
    """
    api_key = get_env("FINNHUB_API_KEY")

    url = f"{FINNHUB_BASE_URL}/calendar/economic"
    params = {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "token": api_key,
    }

    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()

    items = payload.get("economicCalendar", []) or []
    out: list[CalendarEvent] = []

    for it in items:
        ccy = (it.get("currency") or "UNK").strip().upper()
        if filter_currencies and ccy not in set(filter_currencies):
            continue

        country = str(it.get("country") or "")
        event = str(it.get("event") or it.get("name") or "Unknown")
        dt_utc = _to_iso_utc(it.get("time"))

        # stable event_id
        raw_id = f"{dt_utc}|{country}|{ccy}|{event}"
        event_id = "FINNHUB_" + hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:12]

        out.append(
            CalendarEvent(
                event_id=event_id,
                datetime_utc=dt_utc,
                country=country,
                ccy=ccy,
                name=event,
                importance=_impact_to_importance5(it.get("impact")),
                actual=it.get("actual"),
                forecast=it.get("estimate"),
                previous=it.get("prev"),
            )
        )

    out.sort(key=lambda e: e.datetime_utc)
    return out
