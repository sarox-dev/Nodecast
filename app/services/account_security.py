"""Security-sensitive account, recovery, permission and audit operations."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid

from app.core.security import JWT_SECRET
from app.services.database import get_users_db

RECOVERY_CODE_COUNT = 12
RECOVERY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
RESET_REQUEST_TTL = 24 * 60 * 60
APPROVED_RESET_TTL = 15 * 60
OWNER_CHALLENGE_TTL = 15 * 60
MODERATOR_DEFAULT_PERMISSIONS = {"manage_members", "manage_member_resets"}


def _digest(purpose: str, value: str) -> str:
    key = hmac.new(JWT_SECRET.encode(), f"nodecast:{purpose}:v1".encode(), hashlib.sha256).digest()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def _random_secret() -> str:
    return secrets.token_urlsafe(48)


def _make_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(20))
    return "NC-" + "-".join(raw[i:i + 4] for i in range(0, 20, 4))


def normalize_recovery_code(value: str) -> str:
    compact = "".join(ch for ch in value.upper() if ch.isalnum())
    return compact if compact.startswith("NC") else "NC" + compact


def audit(event_type: str, actor_user_id: str | None = None, target_user_id: str | None = None, metadata: dict | None = None, conn=None) -> None:
    owns = conn is None
    db = conn or get_users_db()
    try:
        db.execute(
            "INSERT INTO security_audit_log(id,actor_user_id,event_type,target_user_id,created_at,metadata) VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex, actor_user_id, event_type, target_user_id, int(time.time()), json.dumps(metadata or {}, separators=(",", ":"))),
        )
        if owns:
            db.commit()
    finally:
        if owns:
            db.close()


def create_recovery_set(user_id: str, reason: str, actor_user_id: str | None = None) -> list[str]:
    codes = [_make_code() for _ in range(RECOVERY_CODE_COUNT)]
    now = int(time.time())
    set_id = uuid.uuid4().hex
    db = get_users_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE recovery_code_sets SET status='revoked',revoked_at=?,reason=? WHERE user_id=? AND status='active'", (now, reason, user_id))
        db.execute("INSERT INTO recovery_code_sets(id,user_id,status,created_at,reason) VALUES (?,?,?,?,?)", (set_id, user_id, "active", now, reason))
        db.executemany(
            "INSERT INTO recovery_codes(id,set_id,code_hash) VALUES (?,?,?)",
            [(uuid.uuid4().hex, set_id, _digest("recovery-code", normalize_recovery_code(code))) for code in codes],
        )
        audit("recovery_codes_rotated", actor_user_id, user_id, {"reason": reason}, db)
        db.commit()
        return codes
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def recovery_status(user_id: str) -> dict:
    db = get_users_db()
    try:
        row = db.execute(
            """SELECT s.id,s.created_at,COUNT(c.id) total,SUM(CASE WHEN c.used_at IS NULL THEN 1 ELSE 0 END) remaining
               FROM recovery_code_sets s LEFT JOIN recovery_codes c ON c.set_id=s.id
               WHERE s.user_id=? AND s.status='active' GROUP BY s.id,s.created_at ORDER BY s.created_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else {"id": None, "created_at": None, "total": 0, "remaining": 0}
    finally:
        db.close()


def begin_owner_challenge(username: str, recovery_code: str) -> str | None:
    now = int(time.time())
    code_hash = _digest("recovery-code", normalize_recovery_code(recovery_code))
    db = get_users_db()
    try:
        row = db.execute(
            """SELECT u.id,c.code_hash FROM users u JOIN recovery_code_sets s ON s.user_id=u.id AND s.status='active'
               JOIN recovery_codes c ON c.set_id=s.id AND c.used_at IS NULL
               WHERE LOWER(u.username)=LOWER(?) AND u.role='owner' AND u.disabled=0 AND c.code_hash=?""",
            (username.strip(), code_hash),
        ).fetchone()
        if not row or not hmac.compare_digest(row["code_hash"], code_hash):
            return None
        secret = _random_secret()
        db.execute("DELETE FROM owner_reset_challenges WHERE expires_at<=? OR consumed_at IS NOT NULL", (now,))
        db.execute(
            "INSERT INTO owner_reset_challenges(id,user_id,secret_hash,code_hash,expires_at) VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, row["id"], _digest("owner-reset", secret), code_hash, now + OWNER_CHALLENGE_TTL),
        )
        db.commit()
        return secret
    finally:
        db.close()


def complete_owner_recovery(secret: str, password_hash: str) -> tuple[str, list[str]] | None:
    now = int(time.time())
    secret_hash = _digest("owner-reset", secret)
    db = get_users_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        challenge = db.execute(
            "SELECT * FROM owner_reset_challenges WHERE secret_hash=? AND expires_at>? AND consumed_at IS NULL",
            (secret_hash, now),
        ).fetchone()
        if not challenge:
            db.rollback()
            return None
        codes = [_make_code() for _ in range(RECOVERY_CODE_COUNT)]
        set_id = uuid.uuid4().hex
        valid_code = db.execute(
            """SELECT c.id FROM recovery_codes c JOIN recovery_code_sets s ON s.id=c.set_id
               WHERE s.user_id=? AND s.status='active' AND c.code_hash=? AND c.used_at IS NULL""",
            (challenge["user_id"], challenge["code_hash"]),
        ).fetchone()
        if not valid_code:
            db.rollback()
            return None
        db.execute("UPDATE recovery_codes SET used_at=? WHERE id=?", (now, valid_code["id"]))
        db.execute("UPDATE recovery_code_sets SET status='revoked',revoked_at=?,reason='owner_recovery' WHERE user_id=? AND status='active'", (now, challenge["user_id"]))
        db.execute("UPDATE users SET password_hash=?,token_version=token_version+1,recovery_setup_complete=1 WHERE id=?", (password_hash, challenge["user_id"]))
        db.execute("DELETE FROM web_sessions WHERE active_user_id=? OR id_hash IN (SELECT session_id_hash FROM web_session_accounts WHERE user_id=?)", (challenge["user_id"], challenge["user_id"]))
        db.execute("DELETE FROM password_reset_requests WHERE user_id=?", (challenge["user_id"],))
        db.execute("UPDATE owner_reset_challenges SET consumed_at=? WHERE user_id=?", (now, challenge["user_id"]))
        db.execute("INSERT INTO recovery_code_sets(id,user_id,status,created_at,reason) VALUES (?,?,?,?,?)", (set_id, challenge["user_id"], "active", now, "owner_recovery"))
        db.executemany("INSERT INTO recovery_codes(id,set_id,code_hash) VALUES (?,?,?)", [(uuid.uuid4().hex, set_id, _digest("recovery-code", normalize_recovery_code(code))) for code in codes])
        audit("owner_recovered", challenge["user_id"], challenge["user_id"], {}, db)
        db.commit()
        return challenge["user_id"], codes
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_member_reset_request(username: str, user_agent: str) -> str:
    secret = _random_secret()
    now = int(time.time())
    db = get_users_db()
    try:
        user = db.execute("SELECT id,role,disabled FROM users WHERE LOWER(username)=LOWER(?)", (username.strip(),)).fetchone()
        db.execute("DELETE FROM password_reset_requests WHERE expires_at<=?", (now,))
        if user and user["role"] in {"member", "moderator"} and not user["disabled"]:
            db.execute("UPDATE password_reset_requests SET status='superseded' WHERE user_id=? AND status IN ('pending','approved')", (user["id"],))
            db.execute(
                "INSERT INTO password_reset_requests(id,user_id,secret_hash,status,created_at,expires_at,user_agent) VALUES (?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, user["id"], _digest("member-reset", secret), "pending", now, now + RESET_REQUEST_TTL, user_agent[:300]),
            )
            audit("password_reset_requested", None, user["id"], {}, db)
        db.commit()
        return secret
    finally:
        db.close()


def reset_request_status(secret: str) -> dict:
    now = int(time.time())
    db = get_users_db()
    try:
        row = db.execute("SELECT status,expires_at,approved_at FROM password_reset_requests WHERE secret_hash=?", (_digest("member-reset", secret),)).fetchone()
        if not row or row["expires_at"] <= now:
            return {"status": "pending"}
        if row["status"] == "approved" and (not row["approved_at"] or row["approved_at"] + APPROVED_RESET_TTL <= now):
            return {"status": "expired"}
        return {"status": row["status"]}
    finally:
        db.close()


def complete_member_reset(secret: str, password_hash: str) -> bool:
    now = int(time.time())
    db = get_users_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM password_reset_requests WHERE secret_hash=? AND status='approved' AND approved_at>? AND expires_at>?", (_digest("member-reset", secret), now - APPROVED_RESET_TTL, now)).fetchone()
        if not row:
            db.rollback()
            return False
        db.execute("UPDATE users SET password_hash=?,token_version=token_version+1 WHERE id=?", (password_hash, row["user_id"]))
        db.execute("DELETE FROM web_sessions WHERE active_user_id=? OR id_hash IN (SELECT session_id_hash FROM web_session_accounts WHERE user_id=?)", (row["user_id"], row["user_id"]))
        db.execute("UPDATE password_reset_requests SET status=CASE WHEN id=? THEN 'consumed' ELSE 'superseded' END,consumed_at=? WHERE user_id=? AND status IN ('pending','approved')", (row["id"], now, row["user_id"]))
        audit("password_reset_completed", row["user_id"], row["user_id"], {}, db)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def has_permission(user: dict, permission: str) -> bool:
    if user.get("role") == "owner":
        return True
    if user.get("role") != "moderator":
        return False
    db = get_users_db()
    try:
        rows = [row["permission"] for row in db.execute("SELECT permission FROM moderator_permissions WHERE user_id=?", (user["id"],))]
        if not rows:
            return permission in MODERATOR_DEFAULT_PERMISSIONS
        return permission in set(rows)
    finally:
        db.close()


def revoke_user_sessions(user_id: str) -> None:
    db = get_users_db()
    try:
        db.execute("DELETE FROM web_sessions WHERE active_user_id=? OR id_hash IN (SELECT session_id_hash FROM web_session_accounts WHERE user_id=?)", (user_id, user_id))
        db.execute("UPDATE users SET token_version=token_version+1 WHERE id=?", (user_id,))
        db.commit()
    finally:
        db.close()
