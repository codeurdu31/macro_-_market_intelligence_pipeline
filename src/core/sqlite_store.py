from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.data_sources.models import SourceDoc


DB_PATH = Path("db/warehouse.db")
SCHEMA_PATH = Path("db/schema.sql")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    return con


def init_db() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Missing schema file: {SCHEMA_PATH}")

    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with connect() as con:
        con.executescript(sql)


def upsert_source_docs(docs: Iterable[SourceDoc]) -> int:
    """
    Insert docs into source_docs.
    If source_id already exists, we replace the row (simple & safe).
    """
    n = 0
    with connect() as con:
        cur = con.cursor()
        for d in docs:
            cur.execute(
                """
                INSERT OR REPLACE INTO source_docs
                (source_id, source_type, provider, title, published_at, url, text, ingested_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.source_id,
                    d.source_type,
                    d.provider,
                    d.title,
                    d.published_at,
                    d.url,
                    d.text,
                    _utc_now(),
                ),
            )
            n += 1
        con.commit()
    return n


def insert_macro_signal(source_id: str, signal: dict[str, Any]) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT INTO macro_signals (source_id, extracted_at_utc, signal_json)
            VALUES (?, ?, ?)
            """,
            (source_id, _utc_now(), json.dumps(signal, ensure_ascii=False)),
        )
        con.commit()


def insert_run(run_id: str, n_docs: int, n_issues: int) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO runs (run_id, ts_utc, n_docs, n_issues)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, _utc_now(), int(n_docs), int(n_issues)),
        )
        con.commit()


def insert_issue(run_id: str, issue_type: str, details: dict[str, Any], source_id: str | None = None) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT INTO issues (run_id, issue_type, source_id, details_json, ts_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                issue_type,
                source_id,
                json.dumps(details, ensure_ascii=False),
                _utc_now(),
            ),
        )
        con.commit()
