"""Installation administration endpoints. No knowledge data is exposed here."""
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.account_security import audit, has_permission, revoke_user_sessions
from app.services.auth import get_current_user, hash_password, password_is_supported, verify_password
from app.services.auth_rate_limit import check_rate_limit, clear_failures, rate_key, record_failure
from app.services.database import (
    create_user_in_db, delete_user, get_all_users, get_global_setting, get_user_by_id,
    get_users_db, init_user_db, list_ai_assignments, set_global_setting,
    get_account_mode, member_count,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _control_actor(current_user: dict) -> dict:
    user = get_user_by_id(current_user["user_id"])
    if not user or user.get("disabled") or user.get("role") not in {"owner", "moderator"}:
        raise HTTPException(403, "Administrator permission required")
    return user


def _actor(current_user: dict, permission: str = "manage_members") -> dict:
    user = _control_actor(current_user)
    if not has_permission(user, permission):
        raise HTTPException(403, "Administrator permission required")
    return user


class CreateAccountRequest(BaseModel):
    username: str
    password: str
    role: str = "member"


class AccountActionRequest(BaseModel):
    action: str
    current_password: str
    role: str | None = None


class ResetDecisionRequest(BaseModel):
    decision: str
    current_password: str


class AIPolicyRequest(BaseModel):
    mode: str
    shared_owner_user_id: str | None = None
    exceptions: dict[str, str] = Field(default_factory=dict)

class PermissionRequest(BaseModel):
    permissions: list[str]
    current_password: str

class UserAIPolicyRequest(BaseModel):
    mode: str | None = None
    current_password: str


@router.get("/overview")
def overview(current_user: dict = Depends(get_current_user)):
    actor = _control_actor(current_user)
    db = get_users_db(); now = int(time.time())
    try:
        pending = db.execute("SELECT COUNT(*) c FROM password_reset_requests WHERE status='pending' AND expires_at>?", (now,)).fetchone()["c"]
        sessions = db.execute("SELECT COUNT(*) c FROM web_sessions WHERE expires_at>?", (now,)).fetchone()["c"]
    finally: db.close()
    return {"role": actor["role"], "users": len(get_all_users()), "pending_resets": pending, "active_sessions": sessions, "open_registration": get_global_setting("open_registration", "false") == "true", "account_mode": get_account_mode()}


@router.get("/users")
def users(current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user)
    result = []
    try: ai_policy = json.loads(get_global_setting("ai_policy", "{}") or "{}")
    except json.JSONDecodeError: ai_policy = {}
    for user in get_all_users():
        if actor["role"] != "owner" and user["role"] != "member":
            continue
        item = {k: user[k] for k in ("id", "username", "role", "created_at", "disabled")}
        item["ai_policy_override"] = (ai_policy.get("exceptions") or {}).get(user["id"])
        if actor["role"] == "owner" and user["role"] == "moderator":
            db = get_users_db()
            try:
                saved = [row["permission"] for row in db.execute("SELECT permission FROM moderator_permissions WHERE user_id=?", (user["id"],))]
                item["permissions"] = [value for value in saved if value != "__configured__"] if saved else ["manage_members", "manage_member_resets"]
            finally: db.close()
        result.append(item)
    return {"users": result}


@router.post("/users")
def create_account(req: CreateAccountRequest, current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user)
    role = req.role if req.role in {"member", "moderator"} else "member"
    if get_account_mode() == "personal" and (role != "member" or member_count() >= 1):
        raise HTTPException(409, "Personal installations allow one Library member; change the setup to Shared first")
    if role == "moderator" and actor["role"] != "owner": raise HTTPException(403, "Only the owner can create moderators")
    username = req.username.strip().lower()
    if len(username) < 2: raise HTTPException(400, "Username must be at least 2 characters")
    if not password_is_supported(req.password): raise HTTPException(400, "Password must be between 12 and 72 UTF-8 bytes and must not be commonly used")
    db = get_users_db()
    try:
        if db.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)", (username,)).fetchone(): raise HTTPException(409, "Username already exists")
    finally: db.close()
    uid = create_user_in_db(username, hash_password(req.password), role=role); init_user_db(uid)
    audit("account_created", actor["id"], uid, {"role": role})
    return {"success": True, "user_id": uid}


@router.post("/users/{user_id}/action")
def account_action(user_id: str, req: AccountActionRequest, request: Request, current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user); target = get_user_by_id(user_id)
    if not target: raise HTTPException(404, "User not found")
    key = rate_key(request, "admin-reauth", actor["id"]); check_rate_limit(key)
    if not verify_password(req.current_password, actor["password_hash"]): record_failure(key); raise HTTPException(401, "Current password is incorrect")
    clear_failures(key)
    if target["role"] == "owner": raise HTTPException(400, "The owner account cannot be modified here")
    if actor["role"] != "owner" and target["role"] != "member": raise HTTPException(403, "Moderator scope exceeded")
    db = get_users_db()
    try:
        if req.action in {"disable", "enable"}:
            disabled = 1 if req.action == "disable" else 0
            db.execute("UPDATE users SET disabled=?,token_version=token_version+1 WHERE id=?", (disabled, user_id)); db.commit()
            if disabled: revoke_user_sessions(user_id)
        elif req.action == "set_role":
            if actor["role"] != "owner" or req.role not in {"member", "moderator"}: raise HTTPException(403, "Only the owner can assign this role")
            db.execute("UPDATE users SET role=?,is_admin=0,token_version=token_version+1 WHERE id=?", (req.role, user_id)); db.commit(); revoke_user_sessions(user_id)
        elif req.action == "delete":
            db.close(); delete_user(user_id); db = None
        else: raise HTTPException(400, "Unsupported account action")
    finally:
        if db: db.close()
    audit(f"account_{req.action}", actor["id"], user_id, {"role": req.role} if req.role else {})
    return {"success": True}


@router.put("/users/{user_id}/permissions")
def set_permissions(user_id: str, req: PermissionRequest, request: Request, current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user); target = get_user_by_id(user_id)
    if actor["role"] != "owner": raise HTTPException(403, "Only the owner can grant moderator permissions")
    if not target or target["role"] != "moderator": raise HTTPException(404, "Moderator not found")
    key = rate_key(request, "admin-reauth", actor["id"]); check_rate_limit(key)
    if not verify_password(req.current_password, actor["password_hash"]): record_failure(key); raise HTTPException(401, "Current password is incorrect")
    clear_failures(key)
    allowed = {"manage_members", "manage_member_resets", "manage_ai_policy"}
    selected = set(req.permissions)
    if not selected.issubset(allowed): raise HTTPException(400, "Unknown moderator permission")
    db = get_users_db(); now = int(time.time())
    try:
        db.execute("DELETE FROM moderator_permissions WHERE user_id=?", (user_id,))
        values = ["__configured__", *sorted(selected)]
        db.executemany("INSERT INTO moderator_permissions(user_id,permission,granted_by,created_at) VALUES (?,?,?,?)", [(user_id, permission, actor["id"], now) for permission in values])
        db.commit()
    finally: db.close()
    audit("moderator_permissions_changed", actor["id"], user_id, {"permissions": sorted(selected)})
    return {"success": True, "permissions": sorted(selected)}


@router.put("/users/{user_id}/ai-policy")
def set_user_ai_policy(user_id: str, req: UserAIPolicyRequest, request: Request, current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user); target = get_user_by_id(user_id)
    if actor["role"] != "owner": raise HTTPException(403, "Only the owner can set account AI exceptions")
    if not target or target["role"] != "member": raise HTTPException(404, "Member not found")
    key = rate_key(request, "admin-reauth", actor["id"]); check_rate_limit(key)
    if not verify_password(req.current_password, actor["password_hash"]): record_failure(key); raise HTTPException(401, "Current password is incorrect")
    clear_failures(key)
    if req.mode not in {None, "locked_shared", "default_with_override", "user_managed"}: raise HTTPException(400, "Invalid AI policy mode")
    try: policy = json.loads(get_global_setting("ai_policy", "{}") or "{}")
    except json.JSONDecodeError: policy = {}
    policy.setdefault("mode", "user_managed"); exceptions = policy.setdefault("exceptions", {})
    if req.mode is None: exceptions.pop(user_id, None)
    else: exceptions[user_id] = req.mode
    set_global_setting("ai_policy", json.dumps(policy, separators=(",", ":")))
    audit("user_ai_policy_changed", actor["id"], user_id, {"mode": req.mode or "inherit"})
    return {"success": True, "mode": req.mode}


@router.get("/reset-requests")
def reset_requests(current_user: dict = Depends(get_current_user)):
    _actor(current_user, "manage_member_resets"); now = int(time.time()); db = get_users_db()
    try:
        rows = db.execute("""SELECT r.id,r.status,r.created_at,r.expires_at,r.user_agent,u.username,u.id user_id,u.role
          FROM password_reset_requests r JOIN users u ON u.id=r.user_id WHERE r.status='pending' AND r.expires_at>? ORDER BY r.created_at""", (now,)).fetchall()
        return {"requests": [dict(row) for row in rows]}
    finally: db.close()


@router.post("/reset-requests/{request_id}")
def decide_reset(request_id: str, req: ResetDecisionRequest, request: Request, current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user, "manage_member_resets")
    key = rate_key(request, "admin-reauth", actor["id"]); check_rate_limit(key)
    if not verify_password(req.current_password, actor["password_hash"]): record_failure(key); raise HTTPException(401, "Current password is incorrect")
    clear_failures(key)
    if req.decision not in {"approve", "reject"}: raise HTTPException(400, "Decision must be approve or reject")
    now = int(time.time()); status = "approved" if req.decision == "approve" else "rejected"; db = get_users_db()
    try:
        row = db.execute("SELECT r.user_id,u.role FROM password_reset_requests r JOIN users u ON u.id=r.user_id WHERE r.id=? AND r.status='pending' AND r.expires_at>?", (request_id, now)).fetchone()
        if not row: raise HTTPException(404, "Pending reset request not found")
        if row["role"] == "moderator" and actor["role"] != "owner": raise HTTPException(403, "Only the owner can approve moderator recovery")
        db.execute("UPDATE password_reset_requests SET status=?,approved_at=?,approved_by=? WHERE id=?", (status, now if status == "approved" else None, actor["id"], request_id)); db.commit()
    finally: db.close()
    audit(f"password_reset_{status}", actor["id"], row["user_id"])
    return {"success": True}


@router.get("/audit")
def audit_log(limit: int = 100, current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user)
    if actor["role"] != "owner": raise HTTPException(403, "Owner access required")
    db = get_users_db()
    try:
        rows = db.execute("""SELECT a.id,a.event_type,a.created_at,a.metadata,actor.username actor,target.username target
          FROM security_audit_log a LEFT JOIN users actor ON actor.id=a.actor_user_id LEFT JOIN users target ON target.id=a.target_user_id
          ORDER BY a.created_at DESC LIMIT ?""", (min(max(limit, 1), 500),)).fetchall()
        return {"events": [dict(row) for row in rows]}
    finally: db.close()


@router.get("/ai-policy")
def get_ai_policy(current_user: dict = Depends(get_current_user)):
    _actor(current_user, "manage_ai_policy")
    try: return json.loads(get_global_setting("ai_policy", "{}")) or {"mode": "user_managed", "exceptions": {}}
    except json.JSONDecodeError: return {"mode": "user_managed", "exceptions": {}}


@router.put("/ai-policy")
def set_ai_policy(req: AIPolicyRequest, current_user: dict = Depends(get_current_user)):
    actor = _actor(current_user, "manage_ai_policy")
    if req.mode not in {"locked_shared", "default_with_override", "user_managed"}: raise HTTPException(400, "Invalid AI policy mode")
    current = get_ai_policy(current_user)
    db = get_users_db()
    try: owner_row = db.execute("SELECT id FROM users WHERE role='owner' LIMIT 1").fetchone()
    finally: db.close()
    shared_user_id = req.shared_owner_user_id or current.get("shared_owner_user_id") or (owner_row["id"] if owner_row else actor["id"])
    if actor["role"] != "owner" and req.shared_owner_user_id and req.shared_owner_user_id != current.get("shared_owner_user_id"):
        raise HTTPException(403, "Moderators cannot change the shared provider owner")
    if req.mode != "user_managed":
        assigned = {item["feature"] for item in list_ai_assignments(shared_user_id) if item.get("provider_id") and item.get("model")}
        required = {"atomic_extraction", "recall_synthesis", "entity_extraction", "aggregate_creation"}
        if not required.issubset(assigned):
            raise HTTPException(409, "Configure a provider and model for every AI feature before enabling a shared policy")
    value = {"mode": req.mode, "shared_owner_user_id": shared_user_id, "exceptions": req.exceptions}
    set_global_setting("ai_policy", json.dumps(value, separators=(",", ":"))); audit("ai_policy_changed", actor["id"], None, {"mode": req.mode})
    return value
