"""SQLite persistence for Nodecast's capture + atomic knowledge model."""
import json
import os
import shutil
import sqlite3
import uuid
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.security import CONTENTS_DIR, USERS_DB_PATH, USERS_DATA_DIR
from app.services.ai_crypto import encrypt_api_key
from app.services.text_analysis import ANALYZER_ID, ANALYZER_VERSION, analyze_text, index_terms, language_hint


def _now(): return datetime.now(timezone.utc).isoformat()


def get_users_db():
    os.makedirs(str(CONTENTS_DIR), exist_ok=True)
    conn = sqlite3.connect(str(USERS_DB_PATH)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,is_admin INTEGER DEFAULT 0,created_at TEXT DEFAULT '',token_version INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS global_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS ai_oauth_transactions(state TEXT PRIMARY KEY,user_id TEXT NOT NULL,code_verifier TEXT NOT NULL,nonce TEXT NOT NULL,redirect_uri TEXT NOT NULL,created_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS web_sessions(id_hash TEXT PRIMARY KEY,active_user_id TEXT NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,FOREIGN KEY(active_user_id) REFERENCES users(id) ON DELETE CASCADE);
      CREATE TABLE IF NOT EXISTS web_session_accounts(session_id_hash TEXT NOT NULL,user_id TEXT NOT NULL,authenticated_at INTEGER NOT NULL,PRIMARY KEY(session_id_hash,user_id),FOREIGN KEY(session_id_hash) REFERENCES web_sessions(id_hash) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
      CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry ON web_sessions(expires_at);
      CREATE TABLE IF NOT EXISTS recovery_code_sets(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',created_at INTEGER NOT NULL,revoked_at INTEGER,reason TEXT NOT NULL DEFAULT '',FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
      CREATE TABLE IF NOT EXISTS recovery_codes(id TEXT PRIMARY KEY,set_id TEXT NOT NULL,code_hash TEXT NOT NULL UNIQUE,used_at INTEGER,FOREIGN KEY(set_id) REFERENCES recovery_code_sets(id) ON DELETE CASCADE);
      CREATE INDEX IF NOT EXISTS idx_recovery_sets_user ON recovery_code_sets(user_id,status);
      CREATE TABLE IF NOT EXISTS password_reset_requests(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,secret_hash TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'pending',created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,approved_at INTEGER,approved_by TEXT,consumed_at INTEGER,user_agent TEXT NOT NULL DEFAULT '',FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(approved_by) REFERENCES users(id) ON DELETE SET NULL);
      CREATE INDEX IF NOT EXISTS idx_reset_requests_status ON password_reset_requests(status,expires_at);
      CREATE TABLE IF NOT EXISTS owner_reset_challenges(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,secret_hash TEXT NOT NULL UNIQUE,code_hash TEXT NOT NULL,expires_at INTEGER NOT NULL,consumed_at INTEGER,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
      CREATE TABLE IF NOT EXISTS moderator_permissions(user_id TEXT NOT NULL,permission TEXT NOT NULL,granted_by TEXT NOT NULL,created_at INTEGER NOT NULL,PRIMARY KEY(user_id,permission),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(granted_by) REFERENCES users(id) ON DELETE CASCADE);
      CREATE TABLE IF NOT EXISTS security_audit_log(id TEXT PRIMARY KEY,actor_user_id TEXT,event_type TEXT NOT NULL,target_user_id TEXT,created_at INTEGER NOT NULL,metadata TEXT NOT NULL DEFAULT '{}',FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL,FOREIGN KEY(target_user_id) REFERENCES users(id) ON DELETE SET NULL);
      CREATE INDEX IF NOT EXISTS idx_security_audit_created ON security_audit_log(created_at DESC);
    """)
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "token_version" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")
    if "role" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'member'")
        conn.execute("UPDATE users SET role=CASE WHEN is_admin=1 THEN 'owner' ELSE 'member' END")
        # Pre-session extension JWTs were not bound to an active browser account.
        # Revoke them once when the role/session schema is introduced.
        conn.execute("UPDATE users SET token_version=token_version+1")
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "disabled" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
    if "recovery_setup_complete" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN recovery_setup_complete INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_owner ON users(role) WHERE role='owner'")
    session_columns = {row[1] for row in conn.execute("PRAGMA table_info(web_sessions)")}
    if "last_seen_at" not in session_columns:
        conn.execute("ALTER TABLE web_sessions ADD COLUMN last_seen_at INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE web_sessions SET last_seen_at=created_at WHERE last_seen_at=0")
    if "user_agent" not in session_columns:
        conn.execute("ALTER TABLE web_sessions ADD COLUMN user_agent TEXT NOT NULL DEFAULT ''")
    conn.commit(); return conn


def user_count():
    c=get_users_db()
    try: return c.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] or 0
    finally: c.close()
def user_exists(name):
    c=get_users_db()
    try: return c.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)",(name,)).fetchone() is not None
    finally: c.close()
def create_user_in_db(username,password_hash,is_admin=False,role=None):
    uid=uuid.uuid4().hex[:12]; c=get_users_db()
    try:
        assigned_role = role or ("owner" if is_admin else "member")
        c.execute("INSERT INTO users(id,username,password_hash,is_admin,role,created_at) VALUES (?,?,?,?,?,?)",(uid,username,password_hash,int(assigned_role == "owner"),assigned_role,_now())); c.commit(); return uid
    finally: c.close()
def get_user_by_username(name):
    c=get_users_db()
    try:
        r=c.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)",(name,)).fetchone(); return dict(r) if r else None
    finally: c.close()
def get_user_by_id(uid):
    c=get_users_db()
    try:
        r=c.execute("SELECT id,username,password_hash,is_admin,role,created_at,token_version,disabled,recovery_setup_complete FROM users WHERE id=?",(uid,)).fetchone(); return dict(r) if r else None
    finally: c.close()
def get_all_users():
    c=get_users_db()
    try: return [dict(r) for r in c.execute("SELECT id,username,is_admin,role,created_at,disabled,recovery_setup_complete FROM users ORDER BY created_at")]
    finally: c.close()
def update_password(uid,value):
    c=get_users_db()
    try: c.execute("UPDATE users SET password_hash=?,token_version=token_version+1 WHERE id=?",(value,uid)); c.commit()
    finally: c.close()
def update_username(uid,value):
    c=get_users_db()
    try: c.execute("UPDATE users SET username=?,token_version=token_version+1 WHERE id=?",(value,uid)); c.commit()
    finally: c.close()
def delete_user(uid):
    c=get_users_db()
    try: c.execute("DELETE FROM users WHERE id=?",(uid,)); c.commit()
    finally: c.close()
    p=USERS_DATA_DIR/uid
    if p.exists(): shutil.rmtree(p)
def clear_user_data(uid):
    p=USERS_DATA_DIR/uid
    if p.exists(): shutil.rmtree(p)
    init_user_db(uid)


def _session_hash(secret): return hashlib.sha256(secret.encode("utf-8")).hexdigest()
def web_session_binding(secret): return _session_hash(secret) if secret else ""
def create_web_session(secret, uid, ttl_seconds, user_agent=""):
    now=int(time.time()); sid=_session_hash(secret); c=get_users_db()
    try:
        c.execute("DELETE FROM web_sessions WHERE expires_at<=?",(now,))
        c.execute("INSERT INTO web_sessions(id_hash,active_user_id,created_at,expires_at,last_seen_at,user_agent) VALUES (?,?,?,?,?,?)",(sid,uid,now,now+ttl_seconds,now,user_agent[:300]))
        c.execute("INSERT INTO web_session_accounts VALUES (?,?,?)",(sid,uid,now)); c.commit()
    finally: c.close()
def add_web_session_account(secret, uid, ttl_seconds):
    now=int(time.time()); sid=_session_hash(secret); c=get_users_db()
    try:
        row=c.execute("SELECT 1 FROM web_sessions WHERE id_hash=? AND expires_at>?",(sid,now)).fetchone()
        if not row: return False
        c.execute("INSERT INTO web_session_accounts VALUES (?,?,?) ON CONFLICT(session_id_hash,user_id) DO UPDATE SET authenticated_at=excluded.authenticated_at",(sid,uid,now))
        c.execute("UPDATE web_sessions SET active_user_id=?,expires_at=? WHERE id_hash=?",(uid,now+ttl_seconds,sid)); c.commit(); return True
    finally: c.close()
def get_web_session_user(secret):
    if not secret: return None
    now=int(time.time()); sid=_session_hash(secret); c=get_users_db()
    try:
        r=c.execute("SELECT u.* FROM web_sessions s JOIN users u ON u.id=s.active_user_id WHERE s.id_hash=? AND s.expires_at>? AND u.disabled=0",(sid,now)).fetchone()
        if r: c.execute("UPDATE web_sessions SET last_seen_at=? WHERE id_hash=?",(now,sid)); c.commit()
        return dict(r) if r else None
    finally: c.close()
def list_web_session_accounts(secret):
    now=int(time.time()); sid=_session_hash(secret); c=get_users_db()
    try:
        active=c.execute("SELECT active_user_id FROM web_sessions WHERE id_hash=? AND expires_at>?",(sid,now)).fetchone()
        if not active: return []
        return [dict(r) | {"active": r["id"]==active["active_user_id"]} for r in c.execute("SELECT u.id,u.username,u.role FROM web_session_accounts a JOIN users u ON u.id=a.user_id WHERE a.session_id_hash=? ORDER BY a.authenticated_at DESC",(sid,))]
    finally: c.close()
def switch_web_session_account(secret, uid):
    now=int(time.time()); sid=_session_hash(secret); c=get_users_db()
    try:
        allowed=c.execute("SELECT 1 FROM web_session_accounts a JOIN web_sessions s ON s.id_hash=a.session_id_hash WHERE a.session_id_hash=? AND a.user_id=? AND s.expires_at>?",(sid,uid,now)).fetchone()
        if not allowed: return False
        c.execute("UPDATE web_sessions SET active_user_id=? WHERE id_hash=?",(uid,sid)); c.commit(); return True
    finally: c.close()
def remove_web_session_account(secret, uid):
    sid=_session_hash(secret); c=get_users_db()
    try:
        c.execute("DELETE FROM web_session_accounts WHERE session_id_hash=? AND user_id=?",(sid,uid))
        next_user=c.execute("SELECT user_id FROM web_session_accounts WHERE session_id_hash=? ORDER BY authenticated_at DESC LIMIT 1",(sid,)).fetchone()
        if next_user: c.execute("UPDATE web_sessions SET active_user_id=? WHERE id_hash=?",(next_user["user_id"],sid))
        else: c.execute("DELETE FROM web_sessions WHERE id_hash=?",(sid,))
        c.commit(); return next_user["user_id"] if next_user else None
    finally: c.close()
def web_session_matches(secret, uid):
    user=get_web_session_user(secret); return bool(user and user["id"]==uid)
def web_session_binding_matches(binding, uid):
    if not binding: return False
    now=int(time.time()); c=get_users_db()
    try: return c.execute("SELECT 1 FROM web_sessions WHERE id_hash=? AND active_user_id=? AND expires_at>?",(binding,uid,now)).fetchone() is not None
    finally: c.close()


REGISTER_SETTINGS_PATH=CONTENTS_DIR/"registration.json"
def get_registration_setting():
    stored = get_global_setting("open_registration", "")
    if stored:
        return stored == "true"
    try:
        legacy = bool(json.loads(REGISTER_SETTINGS_PATH.read_text()).get("open_registration", False))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        legacy = False
    set_global_setting("open_registration", "true" if legacy else "false")
    return legacy
def set_registration_setting(value): set_global_setting("open_registration", "true" if value else "false")


def get_user_db_path(uid):
    p=USERS_DATA_DIR/uid; p.mkdir(parents=True,exist_ok=True); return p/"nodecast.db"


SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS captures(id TEXT PRIMARY KEY,capture_type TEXT DEFAULT 'page',source_url TEXT DEFAULT '',source_title TEXT DEFAULT '',source_site_name TEXT DEFAULT '',captured_at TEXT DEFAULT '',saved_at TEXT DEFAULT '',tags TEXT DEFAULT '[]',project TEXT DEFAULT '',raw_path TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_captures_saved_at ON captures(saved_at);
CREATE TABLE IF NOT EXISTS atomics(id TEXT PRIMARY KEY,role TEXT NOT NULL DEFAULT 'evidence',type TEXT NOT NULL,content TEXT DEFAULT '',context_header TEXT DEFAULT '',canonical_key TEXT DEFAULT '',status TEXT DEFAULT 'ready',properties TEXT DEFAULT '{}',source_id TEXT,source_atomics TEXT DEFAULT '[]',confidence REAL DEFAULT 1.0,extracted_by TEXT DEFAULT '',created_at TEXT DEFAULT '',updated_at TEXT DEFAULT '',position INTEGER DEFAULT 0,relevance REAL DEFAULT 0.0,FOREIGN KEY(source_id) REFERENCES captures(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_atomics_role_type ON atomics(role,type); CREATE INDEX IF NOT EXISTS idx_atomics_source ON atomics(source_id); CREATE INDEX IF NOT EXISTS idx_atomics_canonical ON atomics(canonical_key);
CREATE TABLE IF NOT EXISTS atomic_relations(id TEXT PRIMARY KEY,source_atomic_id TEXT NOT NULL,target_atomic_id TEXT NOT NULL,relation_type TEXT NOT NULL,strength REAL DEFAULT 0.5,method TEXT DEFAULT 'ai',reason TEXT DEFAULT '',confidence REAL DEFAULT 0.5,status TEXT DEFAULT 'candidate',context TEXT DEFAULT '',created_at TEXT DEFAULT '',updated_at TEXT DEFAULT '',UNIQUE(source_atomic_id,target_atomic_id,relation_type),FOREIGN KEY(source_atomic_id) REFERENCES atomics(id) ON DELETE CASCADE,FOREIGN KEY(target_atomic_id) REFERENCES atomics(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_ar_source ON atomic_relations(source_atomic_id); CREATE INDEX IF NOT EXISTS idx_ar_target ON atomic_relations(target_atomic_id); CREATE INDEX IF NOT EXISTS idx_ar_type ON atomic_relations(relation_type);
CREATE VIRTUAL TABLE IF NOT EXISTS atomic_fts USING fts5(atomic_id UNINDEXED,content,context_header,canonical_key,tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS atomic_fts_insert AFTER INSERT ON atomics BEGIN INSERT INTO atomic_fts(atomic_id,content,context_header,canonical_key) VALUES(new.id,new.content,new.context_header,new.canonical_key); END;
CREATE TRIGGER IF NOT EXISTS atomic_fts_delete AFTER DELETE ON atomics BEGIN DELETE FROM atomic_fts WHERE atomic_id=old.id; END;
CREATE TRIGGER IF NOT EXISTS atomic_fts_update AFTER UPDATE OF content,context_header,canonical_key ON atomics BEGIN DELETE FROM atomic_fts WHERE atomic_id=old.id; INSERT INTO atomic_fts(atomic_id,content,context_header,canonical_key) VALUES(new.id,new.content,new.context_header,new.canonical_key); END;
CREATE TABLE IF NOT EXISTS atomic_lexical_documents(atomic_id TEXT PRIMARY KEY,analyzer_id TEXT NOT NULL,analyzer_version TEXT NOT NULL,terms TEXT NOT NULL DEFAULT '',scripts TEXT NOT NULL DEFAULT '[]',language_tag TEXT NOT NULL DEFAULT 'und',language_confidence REAL NOT NULL DEFAULT 0.0,updated_at TEXT DEFAULT '',FOREIGN KEY(atomic_id) REFERENCES atomics(id) ON DELETE CASCADE);
CREATE VIRTUAL TABLE IF NOT EXISTS atomic_lexical_fts USING fts5(atomic_id UNINDEXED,terms,tokenize='unicode61 remove_diacritics 0');
CREATE TRIGGER IF NOT EXISTS atomic_lexical_fts_insert AFTER INSERT ON atomic_lexical_documents BEGIN INSERT INTO atomic_lexical_fts(atomic_id,terms) VALUES(new.atomic_id,new.terms); END;
CREATE TRIGGER IF NOT EXISTS atomic_lexical_fts_delete AFTER DELETE ON atomic_lexical_documents BEGIN DELETE FROM atomic_lexical_fts WHERE atomic_id=old.atomic_id; END;
CREATE TRIGGER IF NOT EXISTS atomic_lexical_fts_update AFTER UPDATE OF terms ON atomic_lexical_documents BEGIN DELETE FROM atomic_lexical_fts WHERE atomic_id=old.atomic_id; INSERT INTO atomic_lexical_fts(atomic_id,terms) VALUES(new.atomic_id,new.terms); END;
CREATE TABLE IF NOT EXISTS atomic_embeddings(atomic_id TEXT NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,model_revision TEXT DEFAULT '',dimensions INTEGER DEFAULT 0,embedding BLOB NOT NULL,input_hash TEXT DEFAULT '',created_at TEXT DEFAULT '',PRIMARY KEY(atomic_id,provider,model),FOREIGN KEY(atomic_id) REFERENCES atomics(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS memory_feedback(id TEXT PRIMARY KEY,atomic_id TEXT NOT NULL,feedback TEXT NOT NULL,outcome TEXT DEFAULT '',created_at TEXT DEFAULT '',FOREIGN KEY(atomic_id) REFERENCES atomics(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS ai_providers(id TEXT PRIMARY KEY,name TEXT NOT NULL,provider_type TEXT NOT NULL DEFAULT 'openai_compatible',base_url TEXT NOT NULL,api_key_encrypted TEXT DEFAULT '',default_model TEXT DEFAULT '',provider_key TEXT DEFAULT '',api_style TEXT DEFAULT 'openai',created_at TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS ai_oauth_credentials(provider_id TEXT PRIMARY KEY,client_id TEXT NOT NULL,access_token_encrypted TEXT NOT NULL,refresh_token_encrypted TEXT DEFAULT '',id_token_encrypted TEXT DEFAULT '',expires_at TEXT DEFAULT '',account_id TEXT DEFAULT '',account_email TEXT DEFAULT '',granted_scopes TEXT DEFAULT '',updated_at TEXT DEFAULT '',FOREIGN KEY(provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS ai_feature_assignments(id TEXT PRIMARY KEY,feature TEXT UNIQUE NOT NULL,provider_id TEXT NOT NULL,model TEXT NOT NULL,created_at TEXT DEFAULT '',FOREIGN KEY(provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS pending_ai_jobs(id TEXT PRIMARY KEY,capture_id TEXT NOT NULL,feature TEXT NOT NULL,status TEXT DEFAULT 'pending',idempotency_key TEXT DEFAULT '',attempt_count INTEGER DEFAULT 0,max_attempts INTEGER DEFAULT 3,next_retry_at TEXT DEFAULT '',lease_owner TEXT DEFAULT '',lease_expires_at TEXT DEFAULT '',input_version TEXT DEFAULT '',processor_version TEXT DEFAULT '',error_code TEXT DEFAULT '',created_at TEXT DEFAULT '',processed_at TEXT DEFAULT '',error_message TEXT DEFAULT '',FOREIGN KEY(capture_id) REFERENCES captures(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON pending_ai_jobs(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency ON pending_ai_jobs(idempotency_key) WHERE idempotency_key!='';
CREATE TABLE IF NOT EXISTS user_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL DEFAULT '');
"""
def _add_missing_columns(c, table, columns):
    existing = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _lexical_document(content, context_header, canonical_key):
    analysis = analyze_text(" ".join(part for part in (content, context_header, canonical_key) if part), mode="index")
    scripts = sorted({span.script for span in analysis.scripts})
    language_tag, confidence = language_hint(analysis)
    return " ".join(index_terms(content, context_header, canonical_key)), json.dumps(scripts), language_tag, confidence


def _upsert_lexical_document(c, atomic_id, content, context_header, canonical_key):
    terms, scripts, language_tag, confidence = _lexical_document(content, context_header, canonical_key)
    c.execute(
        """INSERT INTO atomic_lexical_documents(atomic_id,analyzer_id,analyzer_version,terms,scripts,language_tag,language_confidence,updated_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(atomic_id) DO UPDATE SET analyzer_id=excluded.analyzer_id,
             analyzer_version=excluded.analyzer_version,terms=excluded.terms,scripts=excluded.scripts,
             language_tag=excluded.language_tag,language_confidence=excluded.language_confidence,
             updated_at=excluded.updated_at""",
        (atomic_id, ANALYZER_ID, ANALYZER_VERSION, terms, scripts, language_tag, confidence, _now()),
    )


def _ensure_lexical_index(c):
    rows = c.execute(
        """SELECT a.id,a.content,a.context_header,a.canonical_key
           FROM atomics a LEFT JOIN atomic_lexical_documents d ON d.atomic_id=a.id
           WHERE d.atomic_id IS NULL OR d.analyzer_id!=? OR d.analyzer_version!=?""",
        (ANALYZER_ID, ANALYZER_VERSION),
    ).fetchall()
    for row in rows:
        _upsert_lexical_document(c, row[0], row[1], row[2], row[3])
    return len(rows)


def init_user_db(uid):
    """Create or non-destructively upgrade a per-user database to schema v2."""
    c=sqlite3.connect(str(get_user_db_path(uid)))
    try:
        # Old installs already have these tables. Add fields before SCHEMA creates
        # indexes/triggers that reference them. Existing knowledge is retained.
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atomics'").fetchone():
            _add_missing_columns(c, "atomics", {
                "role": "TEXT NOT NULL DEFAULT 'evidence'",
                "context_header": "TEXT DEFAULT ''",
                "canonical_key": "TEXT DEFAULT ''",
                "status": "TEXT DEFAULT 'ready'",
                "updated_at": "TEXT DEFAULT ''",
            })
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atomic_relations'").fetchone():
            _add_missing_columns(c, "atomic_relations", {
                "method": "TEXT DEFAULT 'ai'",
                "reason": "TEXT DEFAULT ''",
                "confidence": "REAL DEFAULT 0.5",
                "status": "TEXT DEFAULT 'candidate'",
                "updated_at": "TEXT DEFAULT ''",
            })
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pending_ai_jobs'").fetchone():
            _add_missing_columns(c, "pending_ai_jobs", {
                "idempotency_key": "TEXT DEFAULT ''", "attempt_count": "INTEGER DEFAULT 0",
                "max_attempts": "INTEGER DEFAULT 3", "next_retry_at": "TEXT DEFAULT ''",
                "lease_owner": "TEXT DEFAULT ''", "lease_expires_at": "TEXT DEFAULT ''",
                "input_version": "TEXT DEFAULT ''", "processor_version": "TEXT DEFAULT ''",
                "error_code": "TEXT DEFAULT ''",
            })
        c.executescript(SCHEMA)
        _add_missing_columns(c, "atomic_lexical_documents", {
            "language_tag": "TEXT NOT NULL DEFAULT 'und'",
            "language_confidence": "REAL NOT NULL DEFAULT 0.0",
        })
        _add_missing_columns(c, "atomic_embeddings", {
            "model_revision": "TEXT DEFAULT ''",
            "input_hash": "TEXT DEFAULT ''",
        })
        _add_missing_columns(c, "pending_ai_jobs", {
            "idempotency_key": "TEXT DEFAULT ''", "attempt_count": "INTEGER DEFAULT 0",
            "max_attempts": "INTEGER DEFAULT 3", "next_retry_at": "TEXT DEFAULT ''",
            "lease_owner": "TEXT DEFAULT ''", "lease_expires_at": "TEXT DEFAULT ''",
            "input_version": "TEXT DEFAULT ''", "processor_version": "TEXT DEFAULT ''",
            "error_code": "TEXT DEFAULT ''",
        })
        c.execute("""INSERT INTO atomic_fts(atomic_id,content,context_header,canonical_key)
                     SELECT a.id,a.content,a.context_header,a.canonical_key FROM atomics a
                     WHERE NOT EXISTS (SELECT 1 FROM atomic_fts f WHERE f.atomic_id=a.id)""")
        _ensure_lexical_index(c)
        c.commit()
    finally: c.close()
def get_db(uid):
    p=get_user_db_path(uid)
    if not p.exists(): init_user_db(uid)
    c=sqlite3.connect(str(p)); c.row_factory=sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON"); return c
def init_db():
    c=get_users_db()
    try: user_ids=[row["id"] for row in c.execute("SELECT id FROM users")]
    finally: c.close()
    for uid in user_ids: init_user_db(uid)


def insert_capture_ref(user_id,capture_id,capture_type,source_url,source_title,source_site_name,captured_at,saved_at,tags,project,raw_path):
    c=get_db(user_id)
    try: c.execute("INSERT INTO captures VALUES (?,?,?,?,?,?,?,?,?,?)",(capture_id,capture_type,source_url,source_title,source_site_name,captured_at,saved_at,json.dumps(tags),project,raw_path)); c.commit()
    finally: c.close()
def _capture(r):
    d=dict(r)
    try: d["tags"]=json.loads(d.get("tags") or "[]")
    except json.JSONDecodeError: d["tags"]=[]
    return d
def get_capture_ref(uid,cid):
    c=get_db(uid)
    try:
        r=c.execute("SELECT * FROM captures WHERE id=?",(cid,)).fetchone(); return _capture(r) if r else None
    finally: c.close()
def list_captures(uid,limit=50,offset=0):
    c=get_db(uid)
    try: return [_capture(r) for r in c.execute("SELECT * FROM captures ORDER BY saved_at DESC LIMIT ? OFFSET ?",(limit,offset))]
    finally: c.close()
def delete_capture_ref(uid,cid):
    c=get_db(uid)
    try: cur=c.execute("DELETE FROM captures WHERE id=?",(cid,)); c.commit(); return cur.rowcount>0
    finally: c.close()
def search_captures(uid,q):
    c=get_db(uid); p=f"%{q}%"
    try: return [_capture(r) for r in c.execute("SELECT * FROM captures WHERE source_title LIKE ? OR source_url LIKE ? OR tags LIKE ? OR project LIKE ? ORDER BY saved_at DESC LIMIT 100",(p,p,p,p))]
    finally: c.close()
def count_captures(uid):
    c=get_db(uid)
    try: return c.execute("SELECT COUNT(*) c FROM captures").fetchone()["c"] or 0
    finally: c.close()


def resolve_ai_config_user(uid):
    """Return the account whose provider configuration applies to this user."""
    try:
        policy = json.loads(get_global_setting("ai_policy", "{}") or "{}")
    except json.JSONDecodeError:
        policy = {}
    mode = (policy.get("exceptions") or {}).get(uid, policy.get("mode", "user_managed"))
    shared_uid = policy.get("shared_owner_user_id")
    if not shared_uid or mode == "user_managed":
        return uid
    if mode == "locked_shared":
        return shared_uid
    if mode == "default_with_override":
        c = get_db(uid)
        try:
            has_own = c.execute("SELECT 1 FROM ai_providers LIMIT 1").fetchone() is not None
        finally:
            c.close()
        return uid if has_own else shared_uid
    return uid


def get_owned_ai_provider(uid,pid):
    c=get_db(uid)
    try:
        r=c.execute("SELECT * FROM ai_providers WHERE id=?",(pid,)).fetchone(); return dict(r) if r else None
    finally: c.close()


def list_owned_ai_providers(uid):
    c=get_db(uid)
    try: return [dict(r) for r in c.execute("SELECT * FROM ai_providers ORDER BY created_at")]
    finally: c.close()
def list_ai_providers(uid):
    return list_owned_ai_providers(resolve_ai_config_user(uid))
def get_ai_provider(uid,pid):
    c=get_db(resolve_ai_config_user(uid))
    try:
        r=c.execute("SELECT * FROM ai_providers WHERE id=?",(pid,)).fetchone(); return dict(r) if r else None
    finally: c.close()
def create_ai_provider(uid,name,base_url,api_key="",provider_type="openai_compatible",provider_key="",api_style="openai"):
    pid=uuid.uuid4().hex[:12]; c=get_db(uid)
    try: c.execute("INSERT INTO ai_providers(id,name,provider_type,base_url,api_key_encrypted,provider_key,api_style,created_at) VALUES (?,?,?,?,?,?,?,?)",(pid,name,provider_type,base_url,encrypt_api_key(api_key) if api_key else "",provider_key,api_style,_now())); c.commit()
    finally: c.close()
    return get_owned_ai_provider(uid,pid)
def update_ai_provider(uid,pid,name=None,base_url=None,api_key=None,default_model=None):
    fields=[]; vals=[]
    for key,val in (("name",name),("base_url",base_url),("default_model",default_model)):
        if val is not None: fields.append(f"{key}=?"); vals.append(val)
    if api_key is not None: fields.append("api_key_encrypted=?"); vals.append(encrypt_api_key(api_key) if api_key else "")
    if fields:
        c=get_db(uid)
        try: c.execute(f"UPDATE ai_providers SET {','.join(fields)} WHERE id=?",vals+[pid]); c.commit()
        finally: c.close()
    return get_owned_ai_provider(uid,pid)
def delete_ai_provider(uid,pid):
    c=get_db(uid)
    try: cur=c.execute("DELETE FROM ai_providers WHERE id=?",(pid,)); c.commit(); return cur.rowcount>0
    finally: c.close()


def save_ai_oauth_credentials(uid, provider_id, client_id, access_token, refresh_token="", id_token="", expires_at="", account_id="", account_email="", granted_scopes=""):
    c=get_db(uid)
    try:
        c.execute("""INSERT INTO ai_oauth_credentials VALUES (?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(provider_id) DO UPDATE SET client_id=excluded.client_id,access_token_encrypted=excluded.access_token_encrypted,
                     refresh_token_encrypted=excluded.refresh_token_encrypted,id_token_encrypted=excluded.id_token_encrypted,expires_at=excluded.expires_at,
                     account_id=excluded.account_id,account_email=excluded.account_email,granted_scopes=excluded.granted_scopes,updated_at=excluded.updated_at""",
                  (provider_id,client_id,encrypt_api_key(access_token),encrypt_api_key(refresh_token),encrypt_api_key(id_token),expires_at,account_id,account_email,granted_scopes,_now()))
        c.commit()
    finally: c.close()


def get_ai_oauth_credentials(uid, provider_id):
    c=get_db(resolve_ai_config_user(uid))
    try:
        row=c.execute("SELECT * FROM ai_oauth_credentials WHERE provider_id=?",(provider_id,)).fetchone()
        return dict(row) if row else None
    finally: c.close()


def create_ai_oauth_transaction(state, user_id, code_verifier, nonce, redirect_uri):
    c=get_users_db()
    try:
        c.execute("DELETE FROM ai_oauth_transactions WHERE datetime(created_at) < datetime('now','-10 minutes')")
        c.execute("INSERT INTO ai_oauth_transactions VALUES (?,?,?,?,?,?)",(state,user_id,code_verifier,nonce,redirect_uri,_now()))
        c.commit()
    finally: c.close()


def consume_ai_oauth_transaction(state):
    c=get_users_db()
    try:
        row=c.execute("SELECT * FROM ai_oauth_transactions WHERE state=? AND datetime(created_at) >= datetime('now','-10 minutes')",(state,)).fetchone()
        c.execute("DELETE FROM ai_oauth_transactions WHERE state=?",(state,)); c.commit()
        return dict(row) if row else None
    finally: c.close()
def list_ai_assignments(uid):
    c=get_db(resolve_ai_config_user(uid))
    try: return [dict(r) for r in c.execute("SELECT * FROM ai_feature_assignments ORDER BY feature")]
    finally: c.close()
def get_ai_assignment_for_feature(uid,feature):
    c=get_db(resolve_ai_config_user(uid))
    try:
        r=c.execute("SELECT * FROM ai_feature_assignments WHERE feature=?",(feature,)).fetchone(); return dict(r) if r else None
    finally: c.close()
def set_ai_assignment(uid,feature,provider_id,model):
    aid=uuid.uuid4().hex[:12]; c=get_db(uid)
    try:
        c.execute("INSERT INTO ai_feature_assignments VALUES (?,?,?,?,?) ON CONFLICT(feature) DO UPDATE SET provider_id=excluded.provider_id,model=excluded.model",(aid,feature,provider_id,model,_now())); c.commit(); return dict(c.execute("SELECT * FROM ai_feature_assignments WHERE feature=?",(feature,)).fetchone())
    finally: c.close()
def delete_ai_assignment(uid,aid):
    c=get_db(uid)
    try: cur=c.execute("DELETE FROM ai_feature_assignments WHERE id=?",(aid,)); c.commit(); return cur.rowcount>0
    finally: c.close()
def get_user_setting(uid,key,default=""):
    c=get_db(uid)
    try:
        r=c.execute("SELECT value FROM user_settings WHERE key=?",(key,)).fetchone(); return r["value"] if r else default
    finally: c.close()
def set_user_setting(uid,key,value):
    c=get_db(uid)
    try: c.execute("INSERT INTO user_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value)); c.commit()
    finally: c.close()
def get_global_setting(key,default=""):
    c=get_users_db()
    try:
        r=c.execute("SELECT value FROM global_settings WHERE key=?",(key,)).fetchone(); return r["value"] if r else default
    finally: c.close()
def set_global_setting(key,value):
    c=get_users_db()
    try: c.execute("INSERT INTO global_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value)); c.commit()
    finally: c.close()


def get_account_mode():
    """Return the deployment account policy selected by the installer."""
    # Legacy installations predate this setting and may already have multiple
    # members, so absence must preserve their shared behavior.
    value = os.getenv("NODECAST_ACCOUNT_MODE", "shared").strip().lower()
    return value if value in {"personal", "shared"} else "shared"


def member_count():
    c = get_users_db()
    try:
        return c.execute("SELECT COUNT(*) c FROM users WHERE role='member'").fetchone()["c"]
    finally:
        c.close()
def count_active_sessions(timeout_minutes=5): return 0


def list_captures_without_ai_data(uid):
    c=get_db(uid); out=[]
    try:
        for r in c.execute("SELECT id,source_title,raw_path FROM captures ORDER BY saved_at DESC"):
            n=c.execute("SELECT COUNT(*) c FROM atomics WHERE source_id=?",(r["id"],)).fetchone()["c"]
            raw_path=Path(r["raw_path"] or "")
            try: raw=json.loads((raw_path/"capture.json").read_text())
            except (FileNotFoundError,json.JSONDecodeError,OSError): raw={}
            selected=((raw.get("anchor") or {}).get("selected_text") or "").strip()
            if selected and (raw_path/"page.html").is_file() and n==0: out.append({"id":r["id"],"source_title":r["source_title"] or ""})
        return out
    finally: c.close()
def add_ai_job(uid,cid,feature,input_version="1",processor_version="1"):
    c=get_db(uid)
    try:
        key=f"{cid}:{feature}:{input_version}:{processor_version}"
        r=c.execute("SELECT id,status FROM pending_ai_jobs WHERE idempotency_key=?",(key,)).fetchone()
        if r: return {"id":r["id"],"status":r["status"]}
        jid=uuid.uuid4().hex[:12]
        c.execute("""INSERT INTO pending_ai_jobs
          (id,capture_id,feature,status,idempotency_key,input_version,processor_version,created_at)
          VALUES (?,?,?,'pending',?,?,?,?)""",(jid,cid,feature,key,input_version,processor_version,_now()))
        c.commit(); return {"id":jid,"status":"pending"}
    finally: c.close()
def get_pending_ai_jobs_grouped(uid):
    c=get_db(uid)
    try: return [dict(r) for r in c.execute("SELECT j.*,COALESCE(c.source_title,'') source_title,COALESCE(a.provider_id,'') provider_id,COALESCE(a.model,'') model FROM pending_ai_jobs j LEFT JOIN captures c ON c.id=j.capture_id LEFT JOIN ai_feature_assignments a ON a.feature=j.feature WHERE (j.status='pending' AND (j.next_retry_at='' OR j.next_retry_at<=?)) OR (j.status='processing' AND j.lease_expires_at!='' AND j.lease_expires_at<=?) ORDER BY a.provider_id,a.model,j.created_at",(_now(),_now()))]
    finally: c.close()
def count_pending_ai_jobs(uid):
    c=get_db(uid)
    try: return c.execute("SELECT COUNT(*) c FROM pending_ai_jobs WHERE status='pending'").fetchone()["c"] or 0
    finally: c.close()
def _finish(uid,jid,status,error=""):
    c=get_db(uid)
    try: c.execute("UPDATE pending_ai_jobs SET status=?,processed_at=?,error_message=? WHERE id=?",(status,_now(),error[:500],jid)); c.commit()
    finally: c.close()
def mark_ai_job_done(uid,jid): _finish(uid,jid,"done")
def mark_ai_job_error(uid,jid,error=""): _finish(uid,jid,"error",error)


def lease_ai_job(uid,jid,owner,lease_seconds=120):
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc); expires=(now+timedelta(seconds=max(10,min(lease_seconds,900)))).isoformat().replace("+00:00","Z")
    now_text=now.isoformat().replace("+00:00","Z"); c=get_db(uid)
    try:
        cur=c.execute("""UPDATE pending_ai_jobs SET status='processing',lease_owner=?,lease_expires_at=?,attempt_count=attempt_count+1
          WHERE id=? AND ((status='pending' AND (next_retry_at='' OR next_retry_at<=?)) OR (status='processing' AND lease_expires_at<=?))""",(owner,expires,jid,now_text,now_text))
        c.commit(); return cur.rowcount==1
    finally: c.close()


def retry_or_fail_ai_job(uid,jid,error_code,error_message,base_delay_seconds=30):
    from datetime import datetime, timedelta, timezone
    c=get_db(uid)
    try:
        row=c.execute("SELECT attempt_count,max_attempts FROM pending_ai_jobs WHERE id=?",(jid,)).fetchone()
        if not row: return "missing"
        terminal=int(row["attempt_count"] or 0)>=int(row["max_attempts"] or 3)
        delay=base_delay_seconds*(2**max(0,int(row["attempt_count"] or 1)-1))
        retry=(datetime.now(timezone.utc)+timedelta(seconds=min(delay,3600))).isoformat().replace("+00:00","Z")
        status="error" if terminal else "pending"
        c.execute("""UPDATE pending_ai_jobs SET status=?,next_retry_at=?,lease_owner='',lease_expires_at='',
          error_code=?,error_message=?,processed_at=? WHERE id=?""",(status,"" if terminal else retry,error_code[:80],error_message[:500],_now() if terminal else "",jid))
        c.commit(); return status
    finally: c.close()


def insert_atomic(user_id,atomic_type,content="",properties=None,source_id=None,source_atomics=None,confidence=1.0,extracted_by="",position=0,relevance=0.0,role="evidence",context_header="",canonical_key="",status="ready"):
    aid=uuid.uuid4().hex[:16]; c=get_db(user_id)
    now=_now()
    try:
        c.execute("INSERT INTO atomics(id,role,type,content,context_header,canonical_key,status,properties,source_id,source_atomics,confidence,extracted_by,created_at,updated_at,position,relevance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(aid,role,atomic_type,content,context_header,canonical_key,status,json.dumps(properties or {}),source_id,json.dumps(source_atomics or []),confidence,extracted_by,now,now,position,relevance))
        _upsert_lexical_document(c, aid, content, context_header, canonical_key)
        c.commit()
        return aid
    finally: c.close()
def insert_atomics_batch(uid,items):
    return [insert_atomic(uid,a.get("type","text"),a.get("content",""),a.get("properties"),a.get("source_id"),a.get("source_atomics"),a.get("confidence",1.0),a.get("extracted_by",""),a.get("position",0),a.get("relevance",0.0),a.get("role","evidence"),a.get("context_header",""),a.get("canonical_key",""),a.get("status","ready")) for a in items]
def _atomic(r):
    d=dict(r)
    for key,default in (("properties",{}),("source_atomics",[])):
        try: d[key]=json.loads(d.get(key) or json.dumps(default))
        except json.JSONDecodeError: d[key]=default
    return d
def get_atomics_by_source(uid,sid):
    c=get_db(uid)
    try: return [_atomic(r) for r in c.execute("SELECT * FROM atomics WHERE source_id=? ORDER BY position,created_at",(sid,))]
    finally: c.close()
def get_atomics_by_type(uid,type_,limit=50):
    c=get_db(uid)
    try: return [_atomic(r) for r in c.execute("SELECT * FROM atomics WHERE type=? ORDER BY relevance DESC,created_at DESC LIMIT ?",(type_,limit))]
    finally: c.close()
def search_atomics(uid,query,type_=None,limit=50):
    c=get_db(uid)
    try:
        analysis=analyze_text(query,mode="query")
        terms=list(analysis.search_terms)
        if not terms: return []
        quoted=[f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:24]]
        stages=[]
        if len(quoted)>1: stages.append(" AND ".join(quoted[:min(6,len(quoted))]))
        stages.append(" OR ".join(quoted))
        found={}
        for stage_index,match in enumerate(stages):
            sql="SELECT a.*,bm25(atomic_lexical_fts) AS search_rank FROM atomic_lexical_fts JOIN atomics a ON a.id=atomic_lexical_fts.atomic_id WHERE atomic_lexical_fts MATCH ?"
            params=[match]
            if type_: sql+=" AND a.type=?"; params.append(type_)
            sql+=" ORDER BY search_rank ASC,a.relevance DESC,a.created_at DESC LIMIT ?"; params.append(max(limit,len(found)+limit))
            for row in c.execute(sql,params):
                item=_atomic(row)
                item["search_stage"]="strict" if stage_index==0 and len(stages)>1 else "relaxed"
                found.setdefault(item["id"],item)
                if len(found)>=limit: break
            if len(found)>=limit: break
        return list(found.values())[:limit]
    finally: c.close()


def rebuild_lexical_index(uid):
    c=get_db(uid)
    try:
        c.execute("DELETE FROM atomic_lexical_documents")
        count=_ensure_lexical_index(c)
        c.commit()
        return {"indexed":count,"analyzer_id":ANALYZER_ID,"analyzer_version":ANALYZER_VERSION}
    finally: c.close()


def upsert_atomic_embedding(uid, atomic_id, provider, model, model_revision, vector, input_hash=""):
    from app.services.semantic_retrieval import pack_vector
    payload = pack_vector(vector)
    c = get_db(uid)
    try:
        if not c.execute("SELECT 1 FROM atomics WHERE id=?", (atomic_id,)).fetchone():
            raise ValueError("Atomic does not belong to this user")
        c.execute(
            """INSERT INTO atomic_embeddings
               (atomic_id,provider,model,model_revision,dimensions,embedding,input_hash,created_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(atomic_id,provider,model) DO UPDATE SET
                 model_revision=excluded.model_revision,dimensions=excluded.dimensions,
                 embedding=excluded.embedding,input_hash=excluded.input_hash,created_at=excluded.created_at""",
            (atomic_id, provider, model, model_revision, len(vector), payload, input_hash, _now()),
        )
        c.commit()
    finally:
        c.close()


def search_atomic_embeddings(uid, query_vector, provider, model, model_revision="", type_=None, limit=50):
    from app.services.semantic_retrieval import cosine_similarity, unpack_vector
    c = get_db(uid)
    try:
        sql = """SELECT a.*,e.dimensions,e.embedding,e.model_revision
                 FROM atomic_embeddings e JOIN atomics a ON a.id=e.atomic_id
                 WHERE e.provider=? AND e.model=?"""
        params = [provider, model]
        if model_revision:
            sql += " AND e.model_revision=?"; params.append(model_revision)
        if type_:
            sql += " AND a.type=?"; params.append(type_)
        rows = []
        for row in c.execute(sql, params):
            try:
                score = cosine_similarity(query_vector, unpack_vector(row["embedding"], row["dimensions"]))
            except ValueError:
                continue
            item = _atomic(row); item.pop("embedding", None)
            item["semantic_score"] = score
            item["search_stage"] = "semantic"
            rows.append(item)
        rows.sort(key=lambda item: (-item["semantic_score"], item["id"]))
        return rows[:limit]
    finally:
        c.close()
def get_atomic_by_id(uid,aid):
    c=get_db(uid)
    try:
        r=c.execute("SELECT * FROM atomics WHERE id=?",(aid,)).fetchone(); return _atomic(r) if r else None
    finally: c.close()
def delete_atomic(uid,aid):
    c=get_db(uid)
    try: cur=c.execute("DELETE FROM atomics WHERE id=?",(aid,)); c.commit(); return cur.rowcount>0
    finally: c.close()
def delete_atomics_by_source(uid,sid):
    c=get_db(uid)
    try: cur=c.execute("DELETE FROM atomics WHERE source_id=?",(sid,)); c.commit(); return cur.rowcount
    finally: c.close()
def insert_atomic_relation(uid,source_atomic_id,target_atomic_id,relation_type,strength=0.5,context="",method="ai",reason="",confidence=None,status="candidate"):
    rid=uuid.uuid4().hex[:16]; c=get_db(uid)
    now=_now(); confidence=strength if confidence is None else confidence
    try:
        c.execute("INSERT INTO atomic_relations(id,source_atomic_id,target_atomic_id,relation_type,strength,method,reason,confidence,status,context,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_atomic_id,target_atomic_id,relation_type) DO UPDATE SET strength=MAX(strength,excluded.strength),method=excluded.method,reason=excluded.reason,confidence=MAX(confidence,excluded.confidence),status=CASE WHEN atomic_relations.status='rejected' THEN 'rejected' ELSE excluded.status END,context=excluded.context,updated_at=excluded.updated_at",(rid,source_atomic_id,target_atomic_id,relation_type,strength,method,reason,confidence,status,context,now,now)); c.commit(); r=c.execute("SELECT id FROM atomic_relations WHERE source_atomic_id=? AND target_atomic_id=? AND relation_type=?",(source_atomic_id,target_atomic_id,relation_type)).fetchone(); return r["id"]
    finally: c.close()
def get_atomic_relations(uid,aid):
    c=get_db(uid)
    try: return [dict(r) for r in c.execute("SELECT * FROM atomic_relations WHERE source_atomic_id=? OR target_atomic_id=? ORDER BY strength DESC",(aid,aid))]
    finally: c.close()
def enrich_atomics_with_sources(uid,items):
    ids=sorted({a.get("source_id") for a in items if a.get("source_id")})
    if not ids: return items
    c=get_db(uid)
    try:
        ph=",".join("?" for _ in ids); sources={r["id"]:dict(r) for r in c.execute(f"SELECT id,source_url,source_title,source_site_name FROM captures WHERE id IN ({ph})",ids)}
    finally: c.close()
    for a in items:
        s=sources.get(a.get("source_id")); a.update({"source_url":s["source_url"] if s else "","source_title":s["source_title"] if s else "","source_site_name":s["source_site_name"] if s else ""})
    return items
def get_atomic_graph(uid,limit=200,include_orphans=False):
    c=get_db(uid)
    try:
        rels=list(c.execute("SELECT * FROM atomic_relations ORDER BY strength DESC LIMIT ?",(limit*4,))); ids={r["source_atomic_id"] for r in rels}|{r["target_atomic_id"] for r in rels}
        if include_orphans: ids|={r["id"] for r in c.execute("SELECT id FROM atomics ORDER BY relevance DESC,created_at DESC LIMIT ?",(limit,))}
        if not ids: return {"nodes":[],"edges":[]}
        ph=",".join("?" for _ in ids); rows=list(c.execute(f"SELECT id,type,content,source_id FROM atomics WHERE id IN ({ph}) LIMIT ?",[*ids,limit])); allowed={r["id"] for r in rows}
        return {"nodes":[{"id":r["id"],"label":r["content"][:80],"type":r["type"],"subtype":r["type"],"source_id":r["source_id"]} for r in rows],"edges":[{"source_id":r["source_atomic_id"],"target_id":r["target_atomic_id"],"relation_type":r["relation_type"],"strength":r["strength"],"context":r["context"]} for r in rels if r["source_atomic_id"] in allowed and r["target_atomic_id"] in allowed]}
    finally: c.close()
