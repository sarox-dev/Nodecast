"""Per-user, disposable cache of validated Recall syntheses."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from app.services.database import get_db, get_user_setting

CACHE_VERSION = "recall-stream-v9-structured-streaming"
MAX_ENTRIES = 200
TTL = timedelta(days=7)


def revision(user_id):
    conn = get_db(user_id)
    try:
        return conn.execute("SELECT revision FROM recall_cache_revision WHERE id=1").fetchone()[0]
    finally:
        conn.close()


def enabled(user_id):
    return get_user_setting(user_id, "recall_cache_enabled", "true") == "true"


def normalize_query(query):
    text = unicodedata.normalize("NFC", query.strip())
    # Quoted/code-like strings and identifiers can be case or punctuation sensitive.
    if re.search(r'[`"“”\n]|(?:\+\+|#|/|\\|_|\b\w+\.\w+\b)', text):
        return text
    return re.sub(r"[?!.]+$", "", text).strip().casefold()


def cache_key(query, packet, revision_value, assignment, provider, view, language):
    payload = {"version": CACHE_VERSION, "query": normalize_query(query), "revision": revision_value,
               "packet": packet, "assignment": assignment, "provider": provider,
               "view": view, "language": language}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def get(user_id, key, expected_revision):
    conn = get_db(user_id)
    try:
        row = conn.execute("SELECT c.answer,c.created_at FROM recall_answer_cache c JOIN recall_cache_revision r ON r.id=1 WHERE c.cache_key=? AND r.revision=?", (key, expected_revision)).fetchone()
        if not row: return None
        try:
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - created > TTL: return None
            answer = json.loads(row["answer"])
        except (ValueError, TypeError, json.JSONDecodeError): return None
        if not isinstance(answer, dict) or answer.get("status") != "success": return None
        return answer, row["created_at"]
    finally:
        conn.close()


def put(user_id, key, answer, expected_revision):
    if not answer or answer.get("status") != "success": return False
    conn = get_db(user_id)
    try:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = conn.execute("INSERT OR REPLACE INTO recall_answer_cache(cache_key,answer,created_at) SELECT ?,?,? WHERE (SELECT revision FROM recall_cache_revision WHERE id=1)=?", (key,json.dumps(answer, ensure_ascii=False),now,expected_revision))
        conn.execute("DELETE FROM recall_answer_cache WHERE cache_key IN (SELECT cache_key FROM recall_answer_cache ORDER BY created_at DESC LIMIT -1 OFFSET ?)", (MAX_ENTRIES,))
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def clear(user_id):
    conn = get_db(user_id)
    try:
        count = conn.execute("DELETE FROM recall_answer_cache").rowcount
        conn.commit()
        return count
    finally:
        conn.close()
