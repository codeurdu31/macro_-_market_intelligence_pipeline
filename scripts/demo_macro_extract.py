from __future__ import annotations

import json
from datetime import datetime, timezone
from src.copilot.llm_client import extract_macro_signal
from src.core.audit import append_jsonl
from src.core.sqlite_store import init_db, insert_macro_signal, upsert_source_docs
from src.data_sources.models import SourceDoc


def main() -> None:
    source_id = "demo_004"

    text = """
The Fed raised its policy rate by 25 bps and signaled further hikes due to persistent inflation.
"""

    signal = extract_macro_signal(text=text, source_id=source_id)

    print("✅ Parsed MacroSignal (Pydantic):")
    print(json.dumps(signal.model_dump(), indent=2, ensure_ascii=False))

    # Write audit log (JSONL)
    append_jsonl("logs/macro_signals.jsonl", {"source_id": source_id, "signal": signal.model_dump()})
    print("\n📌 Logged to logs/macro_signals.jsonl")

    # Optional: store in SQLite with a matching source_doc to satisfy FK
    init_db()
    demo_doc = SourceDoc(
        source_id=source_id,
        source_type="news",
        provider="DEMO",
        title="Demo Macro Text",
        published_at=datetime.now(timezone.utc).isoformat(),
        url="demo://macro_extract",
        text=text.strip(),
    )
    upsert_source_docs([demo_doc])
    insert_macro_signal(source_id=source_id, signal=signal.model_dump())
    print("📌 Inserted into SQLite: macro_signals")


if __name__ == "__main__":
    main()
