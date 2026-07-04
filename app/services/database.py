import sqlite3
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.security import USERS_DB_PATH, USERS_DATA_DIR, CONTENTS_DIR

# ─── Global users DB ──────────────────────────────────────────────

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
    # Add is_admin column if missing (migration)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    except:
        pass  # Already exists
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
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_users() -> list[dict]:
    conn = get_users_db()
    try:
        return [dict(r) for r in conn.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY created_at").fetchall()]
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
    # Remove data directory
    import shutil
    user_dir = USERS_DATA_DIR / user_id
    if user_dir.exists():
        shutil.rmtree(str(user_dir))


def clear_user_data(user_id: str):
    """Clear all items/projects from a user's DB but keep the user."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DELETE FROM items")
        conn.execute("DELETE FROM projects")
        conn.commit()
    finally:
        conn.close()


# ─── Registration setting ─────────────────────────────────────────
REGISTER_SETTINGS_PATH = CONTENTS_DIR / "registration.json"


def get_registration_setting() -> bool:
    """True = anyone can register. False = admin-only."""
    if not REGISTER_SETTINGS_PATH.exists():
        return True  # Default: open registration
    import json
    try:
        data = json.loads(REGISTER_SETTINGS_PATH.read_text())
        return data.get("open_registration", True)
    except:
        return True


def set_registration_setting(open_reg: bool):
    import json
    REGISTER_SETTINGS_PATH.write_text(json.dumps({"open_registration": open_reg}))


# ─── Per-user data DB ─────────────────────────────────────────────

def get_user_db_path(user_id: str) -> Path:
    """Path to a user's data directory and database."""
    user_dir = USERS_DATA_DIR / user_id
    os.makedirs(str(user_dir), exist_ok=True)
    return user_dir / "recollect.db"


def init_user_db(user_id: str):
    """Initialize a user's personal database with schema."""
    db_path = get_user_db_path(user_id)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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


# ─── Migration ────────────────────────────────────────────────────

def migrate_existing_data():
    """Migrate existing contents/recollect.db to a user's per-user database."""
    old_db = CONTENTS_DIR / "recollect.db"
    if not old_db.exists():
        return

    # Check if we've already migrated
    from app.services.auth import hash_password
    first_user = get_all_users()
    if first_user:
        user = first_user[0]
        user_id = user["id"]
    else:
        user_id = "admin"
        now = datetime.now(timezone.utc).isoformat()
        conn = get_users_db()
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, is_admin, created_at) VALUES (?,?,?,?,?)",
            (user_id, "admin", hash_password("changeme"), 1, now),
        )
        conn.commit()
        conn.close()

    target_dir = USERS_DATA_DIR / user_id
    migrated_flag = target_dir / ".migrated"
    if migrated_flag.exists():
        return

    target_db = target_dir / "recollect.db"
    if target_db.exists() and target_db.stat().st_size > 1000:
        migrated_flag.write_text(f"migrated from {old_db} at {datetime.now(timezone.utc).isoformat()}")
        return

    os.makedirs(str(target_dir), exist_ok=True)

    try:
        old_conn = sqlite3.connect(str(old_db))
        old_conn.row_factory = sqlite3.Row

        new_conn = sqlite3.connect(str(target_db))
        new_conn.execute("PRAGMA journal_mode=WAL")
        new_conn.execute("PRAGMA synchronous=NORMAL")
        new_conn.executescript("""
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

        copied = 0
        for row in old_conn.execute("SELECT * FROM items").fetchall():
            new_conn.execute(
                """INSERT INTO items
                   (id, type, content, project, tags,
                    source_url, source_title, source_site_name, source_captured_at,
                    context_before, context_after, context_selection_html, selected_tag, tag_ancestry, saved_at)
                   VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?,?,?)""",
                (row["id"], row["type"], row["content"], row["project"], row["tags"],
                 row["source_url"], row["source_title"], row["source_site_name"], row["source_captured_at"],
                 row["context_before"], row["context_after"], row["context_selection_html"],
                 row["selected_tag"] if "selected_tag" in row.keys() else "",
                 row["tag_ancestry"] if "tag_ancestry" in row.keys() else "",
                 row["saved_at"]),
            )
            copied += 1

        for row in old_conn.execute("SELECT * FROM projects").fetchall():
            new_conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (row["name"],))

        new_conn.commit()
        new_conn.close()
        old_conn.close()

        migrated_flag.write_text(f"migrated {copied} items from {old_db} at {datetime.now(timezone.utc).isoformat()}")

        old_db.rename(old_db.with_suffix(".db.pre-auth"))
        print(f"Migrated {copied} items to {target_db}")
    except Exception as e:
        print(f"Migration error: {e}")


# ─── Legacy compatibility ─────────────────────────────────────────
# Keep these for backwards compatibility during transition

def get_legacy_db():
    """Open the old single-user database (for backward compat during migration)."""
    return get_db("default")


def init_legacy_db_if_needed():
    """Run migration if old DB exists."""
    migrate_existing_data()


# ─── Old init_db kept for import compatibility ────────────────────
def init_db():
    """Legacy: auto-migrate on startup."""
    migrate_existing_data()