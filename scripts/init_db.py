from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.sqlite_store import init_db  # noqa: E402 — supports direct script execution


def main() -> None:
    init_db()
    print("OK: SQLite DB initialized: db/warehouse.db")


if __name__ == "__main__":
    main()
