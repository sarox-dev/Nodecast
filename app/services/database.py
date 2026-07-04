import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.security import CONTENTS_DIR, USERS_DB_PATH, USERS_DATA_DIR

# ─── Global users DB (Auth) ───────────────────────────────────────

def get_users_db():
    """Open the global users database (creates if not exists)."""
    os.makedirs(str(CONTENTS_DIR), exist_ok=True)
    conn = sqlite3.connect(str(USERS_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _init_users_schema(conn)
    return conn


def _init_users_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        );
    """)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()


def user_count() -> int:
    conn = get_users_db()
    try:
        return conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"] or 0
    finally:
        conn.close()


def user_exists(username: str) -> bool:
    conn = get_users_db()
    try:
        return conn.execute(
            "SELECT id FROM users WHERE LOWER(username)=LOWER(?)", (username,)
        ).fetchone() is not None
    finally:
        conn.close()


def create_user_in_db(username: str, password_hash: str, is_admin: bool = False) -> str:
    user_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn = get_users_db()
    try:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, created_at) VALUES (?,?,?,?,?)",
            (user_id, username, password_hash, 1 if is_admin else 0, now),
        )
        conn.commit()
        return user_id
    finally:
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    conn = get_users_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> dict | None:
    conn = get_users_db()
    try:
        row = conn.execute("SELECT id, username, is_admin, created_at FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_users() -> list[dict]:
    conn = get_users_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, username, is_admin, created_at FROM users ORDER BY created_at"
        ).fetchall()]
    finally:
        conn.close()


def update_password(user_id: str, new_hash: str):
    conn = get_users_db()
    try:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user_id))
        conn.commit()
    finally:
        conn.close()


def update_username(user_id: str, new_username: str):
    conn = get_users_db()
    try:
        conn.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))
        conn.commit()
    finally:
        conn.close()


def delete_user(user_id: str):
    """Delete user from users DB and their data directory."""
    conn = get_users_db()
    try:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    import shutil
    user_dir = USERS_DATA_DIR / user_id
    if user_dir.exists():
        shutil.rmtree(str(user_dir))


def clear_user_data(user_id: str):
    """Clear all captures from a user's DB but keep the user."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DELETE FROM captures")
        conn.commit()
    finally:
        conn.close()


# ─── Registration setting ─────────────────────────────────────────

REGISTER_SETTINGS_PATH = CONTENTS_DIR / "registration.json"


def get_registration_setting() -> bool:
    if not REGISTER_SETTINGS_PATH.exists():
        return True
    try:
        data = json.loads(REGISTER_SETTINGS_PATH.read_text())
        return data.get("open_registration", True)
    except Exception:
        return True


def set_registration_setting(open_reg: bool):
    REGISTER_SETTINGS_PATH.write_text(json.dumps({"open_registration": open_reg}))


# ─── Per-user Capture DB ──────────────────────────────────────────

def get_user_db_path(user_id: str) -> Path:
    """Path to a user's data directory and database."""
    user_dir = USERS_DATA_DIR / user_id
    os.makedirs(str(user_dir), exist_ok=True)
    return user_dir / "recollect.db"


def init_user_db(user_id: str):
    """Initialize a user's personal database with the new captures schema."""
    db_path = get_user_db_path(user_id)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS captures (
            id TEXT PRIMARY KEY,
            capture_type TEXT DEFAULT 'page',
            source_url TEXT DEFAULT '',
            source_title TEXT DEFAULT '',
            source_site_name TEXT DEFAULT '',
            captured_at TEXT DEFAULT '',
            saved_at TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            project TEXT DEFAULT '',
            raw_path TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_captures_saved_at ON captures(saved_at);
        CREATE INDEX IF NOT EXISTS idx_captures_project ON captures(project);
        CREATE INDEX IF NOT EXISTS idx_captures_source_url ON captures(source_url);
    """)
    conn.commit()
    conn.close()


def get_db(user_id: str):
    """Open a user's personal database. Initializes if not exists."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        init_user_db(user_id)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ─── Capture CRUD helpers ─────────────────────────────────────────

def insert_capture_ref(
    user_id: str,
    capture_id: str,
    capture_type: str,
    source_url: str,
    source_title: str | None,
    source_site_name: str | None,
    captured_at: str,
    saved_at: str,
    tags: list[str],
    project: str,
    raw_path: str,
):
    """Insert a capture reference row into the user's DB."""
    conn = get_db(user_id)
    try:
        conn.execute(
            """INSERT INTO captures
               (id, capture_type, source_url, source_title, source_site_name,
                captured_at, saved_at, tags, project, raw_path)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                capture_id,
                capture_type,
                source_url,
                source_title or "",
                source_site_name or "",
                captured_at,
                saved_at,
                json.dumps(tags),
                project,
                raw_path,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_capture_ref(user_id: str, capture_id: str) -> dict | None:
    """Get a capture reference row from DB."""
    conn = get_db(user_id)
    try:
        row = conn.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
        if row:
            return _row_to_dict(row)
        return None
    finally:
        conn.close()


def list_captures(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """List capture references, newest first."""
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            "SELECT * FROM captures ORDER BY saved_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_capture_ref(user_id: str, capture_id: str) -> bool:
    """Delete a capture reference. Returns True if existed."""
    conn = get_db(user_id)
    try:
        cur = conn.execute("DELETE FROM captures WHERE id=?", (capture_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def search_captures(user_id: str, query: str) -> list[dict]:
    """Simple text search across capture references."""
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            """SELECT * FROM captures
               WHERE source_url LIKE ? OR source_title LIKE ? OR project LIKE ? OR tags LIKE ?
               ORDER BY saved_at DESC LIMIT 50""",
            (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _row_to_dict(row) -> dict:
    tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
    return {
        "id": row["id"],
        "capture_type": row["capture_type"],
        "source_url": row["source_url"],
        "source_title": row["source_title"],
        "source_site_name": row["source_site_name"],
        "captured_at": row["captured_at"],
        "saved_at": row["saved_at"],
        "tags": tags,
        "project": row["project"],
        "raw_path": row["raw_path"],
    }


# ─── Backward compat stubs (no-op) ────────────────────────────────

def migrate_existing_data():
    pass  # No migration needed — clean start


def init_db():
    pass  # Auto-migrate removed — fresh system


def init_legacy_db_if_needed():
    pass