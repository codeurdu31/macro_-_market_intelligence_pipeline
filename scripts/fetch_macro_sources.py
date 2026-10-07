from __future__ import annotations
from src.core.sqlite_store import init_db, upsert_source_docs, insert_run

import json
from datetime import datetime
from pathlib import Path

from src.data_sources.rss_collector import fetch_rss_sources


def main() -> None:
    docs = fetch_rss_sources(max_items_per_feed=5)
    init_db()
    n = upsert_source_docs(docs)
    insert_run(run_id=f"fetch_macro_{datetime.now().date()}", n_docs=n, n_issues=0)

    Path("data/raw").mkdir(parents=True, exist_ok=True)

    out = f"data/raw/macro_sources_{datetime.now().date()}.json"
    Path(out).write_text(
        json.dumps([d.model_dump() for d in docs], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"✅ Saved {len(docs)} sources -> {out}")


if __name__ == "__main__":
    main()
