"""Public sources for the FX desk; outages never produce substitute data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import feedparser
import httpx
import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict

from src.data_sources.models import SourceDoc

FEEDS = {
    "FED": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "ECB": "https://www.ecb.europa.eu/rss/press.html",
    "BOE": "https://www.bankofengland.co.uk/rss/news",
}
FX_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


class PublicSources:
    """Persist exact HTTP bodies and their collection time; cache only successful GETs."""

    def __init__(self, client: httpx.Client, cache: Path):
        self.client = client
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, url: str, ttl_hours: float = 1) -> tuple[str, datetime]:
        path = self.cache / (sha256(url.encode()).hexdigest() + ".json")
        now = datetime.now(timezone.utc)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            observed = datetime.fromisoformat(saved["observed_at"])
            if timedelta(0) <= now - observed < timedelta(hours=ttl_hours):
                return saved["body"], observed
        response = self.client.get(url)
        response.raise_for_status()
        observed = datetime.now(timezone.utc)
        body = response.text
        path.write_text(
            json.dumps({"url": url, "observed_at": observed.isoformat(), "body": body}),
            encoding="utf-8",
        )
        return body, observed


class ArticleText(HTMLParser):
    """Extract paragraphs/headings within main/article, avoiding script/navigation text."""

    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, bool, bool]] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        parent_main = self.stack[-1][1] if self.stack else False
        parent_blocked = self.stack[-1][2] if self.stack else False
        main = parent_main or tag in {"main", "article"} or attrs.get("id") == "content"
        blocked = parent_blocked or tag in {"script", "style", "nav", "footer", "aside"}
        if tag not in {
            "br",
            "img",
            "meta",
            "link",
            "input",
            "hr",
            "source",
            "wbr",
            "area",
            "embed",
            "param",
            "col",
            "base",
        }:
            self.stack.append((tag, main, blocked))
        if tag in {"p", "h1", "h2", "h3", "li", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                self.stack = self.stack[:index]
                break
        if tag in {"p", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(
            " ".join(line.split()) for line in "".join(self.parts).splitlines() if line.strip()
        )


def collect_documents(
    sources: PublicSources, now: datetime, per_feed: int = 2, max_age_days: int = 30
) -> tuple[list[SourceDoc], list[str]]:
    docs, issues = [], []
    for provider, url in FEEDS.items():
        try:
            body, _ = sources.get(url, 0.25)
            entries = feedparser.parse(body).entries
            if not entries:
                raise ValueError("empty/unreadable RSS")
        except (httpx.HTTPError, ValueError) as exc:
            issues.append(f"{provider} RSS: {type(exc).__name__}")
            continue
        count = 0

        def priority(entry: dict) -> bool:
            return not any(
                term in entry.get("title", "").lower()
                for term in (
                    "monetary policy",
                    "fomc statement",
                    "interest rate",
                    "bank rate",
                    "inflation",
                )
            )

        for entry in sorted(entries, key=priority):
            if count >= per_feed:
                break
            try:
                published = parsedate_to_datetime(entry.get("published", ""))
                if published.tzinfo is None or not timedelta(0) <= now - published <= timedelta(
                    days=max_age_days
                ):
                    continue
                link = entry.get("link", "")
                host = urlparse(link).hostname or ""
                expected = urlparse(url).hostname
                if urlparse(link).scheme != "https" or host != expected:
                    raise ValueError("unexpected article host")
                html, _ = sources.get(link, 24)
                parser = ArticleText()
                parser.feed(html)
                text = parser.text()
                if len(text) < 200:
                    raise ValueError("article text unavailable")
                docs.append(
                    SourceDoc(
                        source_id=f"{provider}_{sha256(link.encode()).hexdigest()[:12]}",
                        source_type="central_bank",
                        provider=provider,
                        title=entry.title,
                        published_at=published.isoformat(),
                        url=link,
                        text=text[:24000],
                    )
                )
                count += 1
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                issues.append(f"{provider} article {entry.get('link', '')}: {type(exc).__name__}")
    return docs, issues


class Expectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    event_id: str
    title: str
    currency: str
    event_at: AwareDatetime
    observed_at: AwareDatetime
    impact: str
    forecast: str
    previous: str
    source: str
    indicator: str | None = None
    value: float | None = None
    unit: str | None = None


# Match exact definitions. ECB refinancing is NOT the deposit facility rate.
RATE_INDICATORS = {
    ("USD", "Federal Funds Rate"): "fed_funds_upper",
    ("EUR", "Main Refinancing Rate"): "ecb_refinancing",
    ("GBP", "Official Bank Rate"): "boe_bank_rate",
}


def collect_expectations(sources: PublicSources, archive: Path) -> list[Expectation]:
    body, observed = sources.get(CALENDAR_URL)
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("invalid calendar payload")
    records = []
    for row in rows:
        title, currency = row["title"], row["country"]
        indicator = RATE_INDICATORS.get((currency, title))
        forecast = str(row.get("forecast") or "")
        value = None
        if indicator and forecast.endswith("%"):
            try:
                value = float(forecast[:-1])
            except ValueError:
                pass
        records.append(
            Expectation(
                event_id=sha256(f"{title}|{currency}|{row['date']}".encode()).hexdigest()[:16],
                title=title,
                currency=currency,
                event_at=row["date"],
                observed_at=observed,
                impact=row.get("impact", "Unknown"),
                forecast=forecast,
                previous=str(row.get("previous") or ""),
                source=CALENDAR_URL,
                indicator=indicator,
                value=value,
                unit="percent" if indicator else None,
            )
        )
    history = load_expectations(archive)
    # Each forecast revision retains its own first-seen timestamp. Never backdate it.
    latest = {r.event_id: r for r in sorted(history, key=lambda r: r.observed_at)}
    new = [
        r
        for r in records
        if r.event_id not in latest
        or (
            r.observed_at > latest[r.event_id].observed_at
            and r.forecast != latest[r.event_id].forecast
        )
    ]
    if new:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with archive.open("a", encoding="utf-8") as stream:
            for record in new:
                stream.write(record.model_dump_json() + "\n")
    return history + new


def load_expectations(archive: Path) -> list[Expectation]:
    if not archive.exists():
        return []
    return [
        Expectation.model_validate_json(line)
        for line in archive.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def parse_fx(xml: str, pairs: list[str], now: datetime) -> pd.DataFrame:
    rows = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("invalid ECB XML") from exc
    for day in root.iter():
        if "time" not in day.attrib:
            continue
        # Conservative availability: following midnight UTC, not an intraday quote.
        available = pd.Timestamp(day.attrib["time"], tz="UTC") + pd.Timedelta(days=1)
        if available > now:
            continue
        rates = {
            "EUR": 1.0,
            **{child.attrib["currency"]: float(child.attrib["rate"]) for child in day},
        }
        if any(not math.isfinite(rate) or rate <= 0 for rate in rates.values()):
            raise ValueError("non-positive FX reference")
        row = {"available_at": available, "reference_date": day.attrib["time"]}
        for pair in pairs:
            if len(pair) != 6 or pair[:3] not in rates or pair[3:] not in rates:
                raise ValueError(f"unsupported pair {pair}")
            row[pair] = rates[pair[3:]] / rates[pair[:3]]
        rows.append(row)
    if not rows:
        raise ValueError("no available FX reference observations")
    frame = pd.DataFrame(rows).set_index("available_at").sort_index()
    if frame.index.has_duplicates:
        raise ValueError("duplicate FX reference dates")
    return frame
