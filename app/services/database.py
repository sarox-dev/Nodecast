"""SQLite persistence for Nodecast's capture + atomic knowledge model."""
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.security import CONTENTS_DIR, USERS_DB_PATH, USERS_DATA_DIR
from app.services.ai_crypto import encrypt_api_key


def _now(): return datetime.now(timezone.utc).isoformat()


def get_users_db():
    os.makedirs(str(CONTENTS_DIR), exist_ok=True)
    conn = sqlite3.connect(str(USERS_DB_PATH)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,is_admin INTEGER DEFAULT 0,created_at TEXT DEFAULT '');
      CREATE TABLE IF NOT EXISTS global_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL DEFAULT '');
    """); conn.commit(); return conn


def user_count():
    c=get_users_db()
    try: return c.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] or 0
    finally: c.close()
def user_exists(name):
    c=get_users_db()
    try: return c.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)",(name,)).fetchone() is not None
    finally: c.close()
def create_user_in_db(username,password_hash,is_admin=False):
    uid=uuid.uuid4().hex[:12]; c=get_users_db()
    try: c.execute("INSERT INTO users VALUES (?,?,?,?,?)",(uid,username,password_hash,int(is_admin),_now())); c.commit(); return uid
    finally: c.close()
def get_user_by_username(name):
    c=get_users_db()
    try:
        r=c.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)",(name,)).fetchone(); return dict(r) if r else None
    finally: c.close()
def get_user_by_id(uid):
    c=get_users_db()
    try:
        r=c.execute("SELECT id,username,is_admin,created_at FROM users WHERE id=?",(uid,)).fetchone(); return dict(r) if r else None
    finally: c.close()
def get_all_users():
    c=get_users_db()
    try: return [dict(r) for r in c.execute("SELECT id,username,is_admin,created_at FROM users ORDER BY created_at")]
    finally: c.close()
def update_password(uid,value):
    c=get_users_db()
    try: c.execute("UPDATE users SET password_hash=? WHERE id=?",(value,uid)); c.commit()
    finally: c.close()
def update_username(uid,value):
    c=get_users_db()
    try: c.execute("UPDATE users SET username=? WHERE id=?",(value,uid)); c.commit()
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


REGISTER_SETTINGS_PATH=CONTENTS_DIR/"registration.json"
def get_registration_setting():
    try: return json.loads(REGISTER_SETTINGS_PATH.read_text()).get("open_registration",True)
    except (FileNotFoundError,json.JSONDecodeError,OSError): return True
def set_registration_setting(value): REGISTER_SETTINGS_PATH.write_text(json.dumps({"open_registration":value}))


def get_user_db_path(uid):
    p=USERS_DATA_DIR/uid; p.mkdir(parents=True,exist_ok=True); return p/"nodecast.db"


SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS captures(id TEXT PRIMARY KEY,capture_type TEXT DEFAULT 'page',source_url TEXT DEFAULT '',source_title TEXT DEFAULT '',source_site_name TEXT DEFAULT '',captured_at TEXT DEFAULT '',saved_at TEXT DEFAULT '',tags TEXT DEFAULT '[]',project TEXT DEFAULT '',raw_path TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_captures_saved_at ON captures(saved_at);
CREATE TABLE IF NOT EXISTS atomics(id TEXT PRIMARY KEY,type TEXT NOT NULL,content TEXT DEFAULT '',properties TEXT DEFAULT '{}',source_id TEXT,source_atomics TEXT DEFAULT '[]',confidence REAL DEFAULT 1.0,extracted_by TEXT DEFAULT '',created_at TEXT DEFAULT '',position INTEGER DEFAULT 0,relevance REAL DEFAULT 0.0,FOREIGN KEY(source_id) REFERENCES captures(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_atomics_type ON atomics(type); CREATE INDEX IF NOT EXISTS idx_atomics_source ON atomics(source_id); CREATE INDEX IF NOT EXISTS idx_atomics_content ON atomics(content);
CREATE TABLE IF NOT EXISTS atomic_relations(id TEXT PRIMARY KEY,source_atomic_id TEXT NOT NULL,target_atomic_id TEXT NOT NULL,relation_type TEXT NOT NULL,strength REAL DEFAULT 0.5,context TEXT DEFAULT '',created_at TEXT DEFAULT '',UNIQUE(source_atomic_id,target_atomic_id,relation_type),FOREIGN KEY(source_atomic_id) REFERENCES atomics(id) ON DELETE CASCADE,FOREIGN KEY(target_atomic_id) REFERENCES atomics(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_ar_source ON atomic_relations(source_atomic_id); CREATE INDEX IF NOT EXISTS idx_ar_target ON atomic_relations(target_atomic_id); CREATE INDEX IF NOT EXISTS idx_ar_type ON atomic_relations(relation_type);
CREATE TABLE IF NOT EXISTS ai_providers(id TEXT PRIMARY KEY,name TEXT NOT NULL,provider_type TEXT NOT NULL DEFAULT 'openai_compatible',base_url TEXT NOT NULL,api_key_encrypted TEXT DEFAULT '',default_model TEXT DEFAULT '',provider_key TEXT DEFAULT '',api_style TEXT DEFAULT 'openai',created_at TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS ai_feature_assignments(id TEXT PRIMARY KEY,feature TEXT UNIQUE NOT NULL,provider_id TEXT NOT NULL,model TEXT NOT NULL,created_at TEXT DEFAULT '',FOREIGN KEY(provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS pending_ai_jobs(id TEXT PRIMARY KEY,capture_id TEXT NOT NULL,feature TEXT NOT NULL,status TEXT DEFAULT 'pending',created_at TEXT DEFAULT '',processed_at TEXT DEFAULT '',error_message TEXT DEFAULT '',FOREIGN KEY(capture_id) REFERENCES captures(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON pending_ai_jobs(status);
CREATE TABLE IF NOT EXISTS user_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL DEFAULT '');
"""
def init_user_db(uid):
    c=sqlite3.connect(str(get_user_db_path(uid)))
    try: c.executescript(SCHEMA); c.commit()
    finally: c.close()
def get_db(uid):
    p=get_user_db_path(uid)
    if not p.exists(): init_user_db(uid)
    c=sqlite3.connect(str(p)); c.row_factory=sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON"); return c
def init_db():
    c=get_users_db(); c.close()


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


def list_ai_providers(uid):
    c=get_db(uid)
    try: return [dict(r) for r in c.execute("SELECT * FROM ai_providers ORDER BY created_at")]
    finally: c.close()
def get_ai_provider(uid,pid):
    c=get_db(uid)
    try:
        r=c.execute("SELECT * FROM ai_providers WHERE id=?",(pid,)).fetchone(); return dict(r) if r else None
    finally: c.close()
def create_ai_provider(uid,name,base_url,api_key="",provider_type="openai_compatible",provider_key="",api_style="openai"):
    pid=uuid.uuid4().hex[:12]; c=get_db(uid)
    try: c.execute("INSERT INTO ai_providers(id,name,provider_type,base_url,api_key_encrypted,provider_key,api_style,created_at) VALUES (?,?,?,?,?,?,?,?)",(pid,name,provider_type,base_url,encrypt_api_key(api_key) if api_key else "",provider_key,api_style,_now())); c.commit()
    finally: c.close()
    return get_ai_provider(uid,pid)
def update_ai_provider(uid,pid,name=None,base_url=None,api_key=None,default_model=None):
    fields=[]; vals=[]
    for key,val in (("name",name),("base_url",base_url),("default_model",default_model)):
        if val is not None: fields.append(f"{key}=?"); vals.append(val)
    if api_key is not None: fields.append("api_key_encrypted=?"); vals.append(encrypt_api_key(api_key) if api_key else "")
    if fields:
        c=get_db(uid)
        try: c.execute(f"UPDATE ai_providers SET {','.join(fields)} WHERE id=?",vals+[pid]); c.commit()
        finally: c.close()
    return get_ai_provider(uid,pid)
def delete_ai_provider(uid,pid):
    c=get_db(uid)
    try: cur=c.execute("DELETE FROM ai_providers WHERE id=?",(pid,)); c.commit(); return cur.rowcount>0
    finally: c.close()
def list_ai_assignments(uid):
    c=get_db(uid)
    try: return [dict(r) for r in c.execute("SELECT * FROM ai_feature_assignments ORDER BY feature")]
    finally: c.close()
def get_ai_assignment_for_feature(uid,feature):
    c=get_db(uid)
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
def add_ai_job(uid,cid,feature):
    c=get_db(uid)
    try:
        r=c.execute("SELECT id FROM pending_ai_jobs WHERE capture_id=? AND feature=? AND status='pending'",(cid,feature)).fetchone()
        if r: return {"id":r["id"],"status":"pending"}
        jid=uuid.uuid4().hex[:12]; c.execute("INSERT INTO pending_ai_jobs(id,capture_id,feature,status,created_at) VALUES (?,?,?,'pending',?)",(jid,cid,feature,_now())); c.commit(); return {"id":jid,"status":"pending"}
    finally: c.close()
def get_pending_ai_jobs_grouped(uid):
    c=get_db(uid)
    try: return [dict(r) for r in c.execute("SELECT j.id,j.capture_id,j.feature,j.created_at,COALESCE(a.provider_id,'') provider_id,COALESCE(a.model,'') model FROM pending_ai_jobs j LEFT JOIN ai_feature_assignments a ON a.feature=j.feature WHERE j.status='pending' ORDER BY a.provider_id,a.model,j.created_at")]
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


def insert_atomic(user_id,atomic_type,content="",properties=None,source_id=None,source_atomics=None,confidence=1.0,extracted_by="",position=0,relevance=0.0):
    aid=uuid.uuid4().hex[:16]; c=get_db(user_id)
    try: c.execute("INSERT INTO atomics VALUES (?,?,?,?,?,?,?,?,?,?,?)",(aid,atomic_type,content,json.dumps(properties or {}),source_id,json.dumps(source_atomics or []),confidence,extracted_by,_now(),position,relevance)); c.commit(); return aid
    finally: c.close()
def insert_atomics_batch(uid,items):
    return [insert_atomic(uid,a.get("type","text"),a.get("content",""),a.get("properties"),a.get("source_id"),a.get("source_atomics"),a.get("confidence",1.0),a.get("extracted_by",""),a.get("position",0),a.get("relevance",0.0)) for a in items]
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
    c=get_db(uid); p=f"%{query}%"
    try:
        rows=c.execute("SELECT * FROM atomics WHERE type=? AND (content LIKE ? OR properties LIKE ?) ORDER BY relevance DESC,created_at DESC LIMIT ?",(type_,p,p,limit)) if type_ else c.execute("SELECT * FROM atomics WHERE content LIKE ? OR properties LIKE ? ORDER BY relevance DESC,created_at DESC LIMIT ?",(p,p,limit))
        return [_atomic(r) for r in rows]
    finally: c.close()
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
def insert_atomic_relation(uid,source_atomic_id,target_atomic_id,relation_type,strength=0.5,context=""):
    rid=uuid.uuid4().hex[:16]; c=get_db(uid)
    try:
        c.execute("INSERT INTO atomic_relations VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_atomic_id,target_atomic_id,relation_type) DO UPDATE SET strength=MAX(strength,excluded.strength),context=excluded.context",(rid,source_atomic_id,target_atomic_id,relation_type,strength,context,_now())); c.commit(); r=c.execute("SELECT id FROM atomic_relations WHERE source_atomic_id=? AND target_atomic_id=? AND relation_type=?",(source_atomic_id,target_atomic_id,relation_type)).fetchone(); return r["id"]
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
