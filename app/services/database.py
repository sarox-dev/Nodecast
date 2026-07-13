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
    return user_dir / "nodecast.db"


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

        CREATE TABLE IF NOT EXISTS ai_providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            provider_type TEXT NOT NULL DEFAULT 'openai_compatible',
            base_url TEXT NOT NULL,
            api_key_encrypted TEXT DEFAULT '',
            default_model TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ai_feature_assignments (
            id TEXT PRIMARY KEY,
            feature TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT DEFAULT '',
            FOREIGN KEY (provider_id) REFERENCES ai_providers(id)
        );

        CREATE TABLE IF NOT EXISTS capture_ai_tags (
            capture_id TEXT PRIMARY KEY,
            tags TEXT DEFAULT '[]',
            summary TEXT DEFAULT '',
            key_concepts TEXT DEFAULT '[]',
            model TEXT DEFAULT '',
            processed_at TEXT DEFAULT '',
            ai_tags_source TEXT DEFAULT '[]',
            FOREIGN KEY (capture_id) REFERENCES captures(id)
        );
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
    # Migration: ensure AI tables exist on existing databases
    _migrate_ai_tables(conn)
    return conn


def _migrate_ai_tables(conn):
    """Add AI tables if they don't exist (migration for existing DBs)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ai_providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            provider_type TEXT NOT NULL DEFAULT 'openai_compatible',
            base_url TEXT NOT NULL,
            api_key_encrypted TEXT DEFAULT '',
            default_model TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ai_feature_assignments (
            id TEXT PRIMARY KEY,
            feature TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT DEFAULT '',
            FOREIGN KEY (provider_id) REFERENCES ai_providers(id)
        );
        CREATE TABLE IF NOT EXISTS capture_ai_tags (
            capture_id TEXT PRIMARY KEY,
            tags TEXT DEFAULT '[]',
            summary TEXT DEFAULT '',
            key_concepts TEXT DEFAULT '[]',
            model TEXT DEFAULT '',
            processed_at TEXT DEFAULT '',
            ai_tags_source TEXT DEFAULT '[]',
            FOREIGN KEY (capture_id) REFERENCES captures(id)
        );
    """)
    conn.commit()


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


# ─── AI Provider CRUD ──────────────────────────────────────────────

import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz


def _now_iso() -> str:
    return _dt.now(_tz.utc).isoformat().replace("+00:00", "Z")


def list_ai_providers(user_id: str) -> list[dict]:
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            "SELECT id, name, provider_type, base_url, default_model, created_at FROM ai_providers ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_ai_provider(user_id: str, provider_id: str) -> dict | None:
    conn = get_db(user_id)
    try:
        row = conn.execute(
            "SELECT * FROM ai_providers WHERE id=?", (provider_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_ai_provider(
    user_id: str, name: str, base_url: str, api_key_encrypted: str, provider_type: str = "openai_compatible"
) -> dict:
    from app.services.ai_crypto import encrypt_api_key

    pid = _uuid.uuid4().hex[:12]
    encrypted = encrypt_api_key(api_key_encrypted)
    now = _now_iso()
    conn = get_db(user_id)
    try:
        conn.execute(
            "INSERT INTO ai_providers (id, name, provider_type, base_url, api_key_encrypted, default_model, created_at) VALUES (?,?,?,?,?,?,?)",
            (pid, name.strip(), provider_type, base_url.strip(), encrypted, "", now),
        )
        conn.commit()
        return {"id": pid, "name": name.strip(), "provider_type": provider_type, "base_url": base_url.strip(), "default_model": "", "created_at": now}
    finally:
        conn.close()


def update_ai_provider(user_id: str, provider_id: str, name: str | None = None, base_url: str | None = None, api_key: str | None = None, default_model: str | None = None) -> dict | None:
    from app.services.ai_crypto import encrypt_api_key

    existing = get_ai_provider(user_id, provider_id)
    if not existing:
        return None
    conn = get_db(user_id)
    try:
        if name is not None:
            conn.execute("UPDATE ai_providers SET name=? WHERE id=?", (name.strip(), provider_id))
        if base_url is not None:
            conn.execute("UPDATE ai_providers SET base_url=? WHERE id=?", (base_url.strip(), provider_id))
        if api_key is not None:
            encrypted = encrypt_api_key(api_key)
            conn.execute("UPDATE ai_providers SET api_key_encrypted=? WHERE id=?", (encrypted, provider_id))
        if default_model is not None:
            conn.execute("UPDATE ai_providers SET default_model=? WHERE id=?", (default_model, provider_id))
        conn.commit()
    finally:
        conn.close()
    return get_ai_provider(user_id, provider_id)


def delete_ai_provider(user_id: str, provider_id: str) -> bool:
    conn = get_db(user_id)
    try:
        conn.execute("DELETE FROM ai_feature_assignments WHERE provider_id=?", (provider_id,))
        cur = conn.execute("DELETE FROM ai_providers WHERE id=?", (provider_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ─── AI Feature Assignments ────────────────────────────────────────


def list_ai_assignments(user_id: str) -> list[dict]:
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            "SELECT * FROM ai_feature_assignments ORDER BY feature"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_ai_assignment_for_feature(user_id: str, feature: str) -> dict | None:
    conn = get_db(user_id)
    try:
        row = conn.execute(
            "SELECT * FROM ai_feature_assignments WHERE feature=?", (feature,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_ai_assignment(user_id: str, feature: str, provider_id: str, model: str) -> dict:
    now = _now_iso()
    conn = get_db(user_id)
    try:
        existing = conn.execute(
            "SELECT id FROM ai_feature_assignments WHERE feature=?", (feature,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE ai_feature_assignments SET provider_id=?, model=? WHERE feature=?",
                (provider_id, model, feature),
            )
            aid = existing["id"]
        else:
            aid = _uuid.uuid4().hex[:12]
            conn.execute(
                "INSERT INTO ai_feature_assignments (id, feature, provider_id, model, created_at) VALUES (?,?,?,?,?)",
                (aid, feature, provider_id, model, now),
            )
        conn.commit()
        return {"id": aid, "feature": feature, "provider_id": provider_id, "model": model}
    finally:
        conn.close()


def delete_ai_assignment(user_id: str, assignment_id: str) -> bool:
    conn = get_db(user_id)
    try:
        cur = conn.execute("DELETE FROM ai_feature_assignments WHERE id=?", (assignment_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ─── Capture AI Tags ───────────────────────────────────────────────


def get_capture_ai_tags(user_id: str, capture_id: str) -> dict | None:
    conn = get_db(user_id)
    try:
        row = conn.execute(
            "SELECT * FROM capture_ai_tags WHERE capture_id=?", (capture_id,)
        ).fetchone()
        if row:
            r = dict(row)
            if isinstance(r.get("tags"), str):
                r["tags"] = json.loads(r["tags"])
            if isinstance(r.get("key_concepts"), str):
                r["key_concepts"] = json.loads(r["key_concepts"])
            if isinstance(r.get("ai_tags_source"), str):
                r["ai_tags_source"] = json.loads(r["ai_tags_source"])
            return r
        return None
    finally:
        conn.close()


def upsert_capture_ai_tags(
    user_id: str,
    capture_id: str,
    tags: list[str],
    summary: str,
    key_concepts: list[str],
    model: str,
    ai_tags_source: list[str],
) -> dict:
    now = _now_iso()
    conn = get_db(user_id)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO capture_ai_tags
               (capture_id, tags, summary, key_concepts, model, processed_at, ai_tags_source)
               VALUES (?,?,?,?,?,?,?)""",
            (capture_id, json.dumps(tags), summary, json.dumps(key_concepts), model, now, json.dumps(ai_tags_source)),
        )
        conn.commit()
        return {"capture_id": capture_id, "tags": tags, "summary": summary, "key_concepts": key_concepts, "model": model, "processed_at": now}
    finally:
        conn.close()


def list_captures_without_ai_tags(user_id: str, limit: int = 100) -> list[dict]:
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            """SELECT c.id, c.source_title, c.source_url, c.saved_at
               FROM captures c
               LEFT JOIN capture_ai_tags t ON c.id = t.capture_id
               WHERE t.capture_id IS NULL
               ORDER BY c.saved_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()