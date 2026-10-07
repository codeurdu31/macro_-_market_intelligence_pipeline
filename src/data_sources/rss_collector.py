from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import httpx
import feedparser

from src.data_sources.models import SourceDoc


DEFAULT_FEEDS = [
    # Fed press releases (official RSS)
    ("FED", "https://www.federalreserve.gov/feeds/press_all.xml"),
    # ECB press releases / speeches (official RSS)
    ("ECB", "https://www.ecb.europa.eu/rss/press.html"),
    # BoE speeches RSS (official RSS)
    ("BOE", "https://www.bankofengland.co.uk/rss/speeches"),
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def fetch_rss_sources(max_items_per_feed: int = 5) -> list[SourceDoc]:
    docs: list[SourceDoc] = []

    headers = {"User-Agent": "fx-risk-copilot/0.1"}

    for provider, url in DEFAULT_FEEDS:
        r = httpx.get(url, headers=headers, timeout=20)
        r.raise_for_status()

        feed = feedparser.parse(r.text)

        for entry in feed.entries[:max_items_per_feed]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            published = getattr(entry, "published", "")
            summary = getattr(entry, "summary", "")

            text = f"{title}\n\n{summary}".strip()
            if not text:
                continue

            source_id = f"{provider}_{_sha(title + link)}"

            docs.append(
                SourceDoc(
                    source_id=source_id,
                    source_type="central_bank",
                    provider=provider,
                    title=title,
                    published_at=published or datetime.now(timezone.utc).isoformat(),
                    url=link or url,
                    text=text[:5000],
                )
            )

    return docs
