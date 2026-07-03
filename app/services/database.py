import sqlite3
import json
import os
from pathlib import Path

# Detect project root: look for the contents dir relative to this file
_current = Path(__file__).resolve()
for parent in [_current] + list(_current.parents):
    candidate = parent / "contents"
    if candidate.is_dir():
        DB_DIR = candidate
        break
else:
    DB_DIR = _current.parent.parent.parent / "contents"

DB_PATH = DB_DIR / "recollect.db"


def get_db():
    os.makedirs(str(DB_DIR), exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            type TEXT DEFAULT 'snippet',
            content TEXT DEFAULT '',
            project TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            source_url TEXT DEFAULT '',
            source_title TEXT DEFAULT '',
            source_site_name TEXT DEFAULT '',
            source_captured_at TEXT DEFAULT '',
            context_before TEXT DEFAULT '',
            context_after TEXT DEFAULT '',
            context_selection_html TEXT DEFAULT '',
            selected_tag TEXT DEFAULT '',
            tag_ancestry TEXT DEFAULT '',
            saved_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY
        );
        CREATE INDEX IF NOT EXISTS idx_items_project ON items(project);
        CREATE INDEX IF NOT EXISTS idx_items_saved_at ON items(saved_at);
    """)
    conn.commit()
    conn.close()