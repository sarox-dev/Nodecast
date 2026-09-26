#!/usr/bin/env python3
"""Reset captured knowledge while preserving accounts, settings and AI providers."""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.database import get_all_users, get_db, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Confirm the destructive knowledge reset")
    args = parser.parse_args()
    if not args.yes:
        parser.error("Pass --yes to confirm. Accounts, settings and AI providers are retained.")

    init_db()
    for user in get_all_users():
        user_id = user["id"]
        conn = get_db(user_id)
        try:
            # Verify the targets before writing. Foreign keys and FTS triggers
            # clean relations, embeddings, feedback and search rows.
            required = {"captures", "atomics", "pending_ai_jobs"}
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables:
                raise RuntimeError(f"Unexpected database schema for {user['username']}")
            before = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in required}
            conn.execute("DELETE FROM pending_ai_jobs")
            conn.execute("DELETE FROM atomics")
            conn.execute("DELETE FROM captures")
            conn.commit()
        finally:
            conn.close()
        raw_dir = ROOT / "contents" / "users" / user_id / "raw"
        if raw_dir.is_dir():
            shutil.rmtree(raw_dir)
        print(f"{user['username']}: cleared {before}; providers/settings preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
