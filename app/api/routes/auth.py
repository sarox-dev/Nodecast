import os
import time

from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel

from app.services.auth import (
    hash_password, verify_password, create_token,
    get_current_user, password_is_supported, set_session_cookie, start_web_session, COOKIE_NAME
)
from app.services.database import (
    init_user_db, user_exists,
    create_user_in_db, get_user_by_username, get_user_by_id,
    get_all_users, update_password, update_username,
    delete_user, clear_user_data,
    user_count, get_registration_setting, set_registration_setting,
    list_web_session_accounts, switch_web_session_account, remove_web_session_account,
    get_web_session_user, web_session_binding,
    get_users_db,
)
from app.services.account_security import (
    begin_owner_challenge, complete_member_reset, complete_owner_recovery,
    create_member_reset_request, create_recovery_set, recovery_status,
    reset_request_status, audit, revoke_user_sessions,
)
from app.services.auth_rate_limit import check_rate_limit, clear_failures, rate_key, record_failure

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Schemas ──────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ChangeUsernameRequest(BaseModel):
    password: str
    new_username: str

class AdminDeleteUserRequest(BaseModel):
    target_user_id: str
    admin_password: str
    action: str  # "delete" or "clear_data"

class SwitchAccountRequest(BaseModel):
    user_id: str

class RecoveryAckRequest(BaseModel):
    saved: bool

class RotateRecoveryRequest(BaseModel):
    current_password: str

class ForgotPasswordRequest(BaseModel):
    username: str

class OwnerRecoveryRequest(BaseModel):
    username: str
    recovery_code: str

class ResetPasswordRequest(BaseModel):
    new_password: str

RECOVERY_REQUEST_COOKIE = "nodecast_recovery_request"
OWNER_RESET_COOKIE = "nodecast_owner_reset"


def _set_private_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(name, value, httponly=True, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", samesite="strict", max_age=max_age, path="/")


# ─── API Token ────────────────────────────────────────────────────

@router.post("/api-token")
def get_api_token(req: LoginRequest, request: Request):
    """Generate an API token for extension use. Accepts login credentials."""
    key = rate_key(request, "api-token", req.username)
    ip_key = rate_key(request, "api-token")
    check_rate_limit(key, ip_key)
    user = get_user_by_username(req.username.strip().lower())
    if not user or not verify_password(req.password, user["password_hash"]):
        record_failure(key, ip_key)
        raise HTTPException(401, "Invalid username or password")
    clear_failures(key)
    session_secret = request.cookies.get(COOKIE_NAME, "")
    active = get_web_session_user(session_secret)
    if not active or active["id"] != user["id"]:
        raise HTTPException(409, "Connect the extension from Nodecast Settings")
    token = create_token(user["id"], user["username"], scope="extension", session_binding=web_session_binding(session_secret))
    return {"token": token, "user_id": user["id"], "username": user["username"]}


# ─── Check ───────────────────────────────────────────────────────
@router.get("/check")
def check_users():
    return {"has_users": user_count() > 0}


# ─── Register ─────────────────────────────────────────────────────
@router.post("/register")
def register(req: RegisterRequest, response: Response, request: Request):
    key = rate_key(request, "register")
    check_rate_limit(key)
    record_failure(key)
    username = req.username.strip().lower()
    if not username or len(username) < 2:
        raise HTTPException(400, "Username must be at least 2 characters")
    # First user is admin
    is_admin = user_count() == 0
    if not password_is_supported(req.password, owner=is_admin):
        minimum = 16 if is_admin else 12
        raise HTTPException(400, f"Password must be between {minimum} and 72 UTF-8 bytes and must not be commonly used")

    if user_exists(username):
        raise HTTPException(409, "Username already exists")

    # Check if registration is open
    if not is_admin and not get_registration_setting():
        raise HTTPException(403, "Registration is closed. Contact your admin.")

    user_id = create_user_in_db(username, hash_password(req.password), is_admin=is_admin, role="owner" if is_admin else "member")
    if not is_admin:
        init_user_db(user_id)

    start_web_session(response, user_id, request.cookies.get(COOKIE_NAME, ""), request.headers.get("user-agent", ""))
    clear_failures(key)
    audit("account_created", user_id, user_id, {"role": "owner" if is_admin else "member"})
    return {
        "success": True,
        "requires_recovery_setup": is_admin,
        "user": {"user_id": user_id, "username": username, "is_admin": is_admin, "role": "owner" if is_admin else "member"},
    }


# ─── Login ────────────────────────────────────────────────────────
@router.post("/login")
def login(req: LoginRequest, response: Response, request: Request):
    username = req.username.strip().lower()
    key = rate_key(request, "login", username)
    ip_key = rate_key(request, "login")
    check_rate_limit(key, ip_key)
    user = get_user_by_username(username)
    if not user or user.get("disabled"):
        record_failure(key, ip_key)
        raise HTTPException(401, "Invalid username or password")
    if not verify_password(req.password, user["password_hash"]):
        record_failure(key, ip_key)
        raise HTTPException(401, "Invalid username or password")

    clear_failures(key)
    start_web_session(response, user["id"], request.cookies.get(COOKIE_NAME, ""), request.headers.get("user-agent", ""))
    return {
        "success": True,
        "requires_recovery_setup": user.get("role") == "owner" and not bool(user.get("recovery_setup_complete")),
        "user": {"user_id": user["id"], "username": username, "is_admin": bool(user["is_admin"]), "role": user.get("role", "member")},
    }


# ─── Logout ──────────────────────────────────────────────────────
@router.post("/logout")
def logout(response: Response, request: Request, current_user: dict = Depends(get_current_user)):
    secret = request.cookies.get(COOKIE_NAME, "")
    next_user = remove_web_session_account(secret, current_user["user_id"]) if secret else None
    if not next_user:
        response.delete_cookie(key=COOKIE_NAME, path="/", samesite="strict")
    return {"success": True, "message": "Logged out", "has_active_account": bool(next_user)}

@router.get("/accounts")
def session_accounts(request: Request, current_user: dict = Depends(get_current_user)):
    secret = request.cookies.get(COOKIE_NAME, "")
    accounts = list_web_session_accounts(secret) if secret else []
    if not accounts:
        user = get_user_by_id(current_user["user_id"])
        accounts = [{"id": user["id"], "username": user["username"], "role": user.get("role", "member"), "active": True}]
    return {"accounts": accounts}

@router.post("/switch-account")
def switch_account(req: SwitchAccountRequest, request: Request, current_user: dict = Depends(get_current_user)):
    secret = request.cookies.get(COOKIE_NAME, "")
    if not secret or not switch_web_session_account(secret, req.user_id):
        raise HTTPException(403, "Account is not authenticated in this browser session")
    target = get_user_by_id(req.user_id)
    return {"success": True, "user": {"user_id": target["id"], "username": target["username"], "role": target.get("role", "member")}}


# ─── Me ───────────────────────────────────────────────────────────
@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(404, "User not found")
    return {
        "user_id": user["id"],
        "username": user["username"],
        "is_admin": bool(user["is_admin"]),
        "role": user.get("role", "owner" if user["is_admin"] else "member"),
        "created_at": user["created_at"],
        "recovery_setup_complete": bool(user.get("recovery_setup_complete")),
    }


# ─── Change password ─────────────────────────────────────────────
@router.post("/change-password")
def change_password(req: ChangePasswordRequest, response: Response, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(401, "Current password is incorrect")
    is_owner = user.get("role") == "owner"
    if not password_is_supported(req.new_password, owner=is_owner):
        minimum = 16 if is_owner else 12
        raise HTTPException(400, f"New password must be between {minimum} and 72 UTF-8 bytes and must not be commonly used")
    update_password(user["id"], hash_password(req.new_password))
    refreshed = get_user_by_id(user["id"])
    revoke_user_sessions(user["id"])
    start_web_session(response, refreshed["id"], "")
    audit("password_changed", user["id"], user["id"])
    return {"success": True, "message": "Password updated"}


# ─── Change username ─────────────────────────────────────────────
@router.post("/change-username")
def change_username(req: ChangeUsernameRequest, response: Response, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Password is incorrect")
    new_username = req.new_username.strip().lower()
    if not new_username or len(new_username) < 2:
        raise HTTPException(400, "Username must be at least 2 characters")
    if new_username != user["username"] and user_exists(new_username):
        raise HTTPException(409, "Username already taken")
    update_username(user["id"], new_username)
    start_web_session(response, user["id"], "")
    audit("username_changed", user["id"], user["id"])
    return {"success": True, "message": "Username updated"}


# ─── Users list (admin only) ─────────────────────────────────────
@router.get("/users")
def list_users(current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user or not user["is_admin"]:
        raise HTTPException(403, "Admin access required")
    users = get_all_users()
    return {
        "users": [
            {
                "user_id": u["id"],
                "username": u["username"],
                "is_admin": bool(u["is_admin"]),
                "role": u.get("role", "owner" if u["is_admin"] else "member"),
                "created_at": u["created_at"],
            }
            for u in users
        ]
    }


# ─── Admin: delete user or clear data ────────────────────────────
@router.post("/admin/user")
def admin_user_action(req: AdminDeleteUserRequest, current_user: dict = Depends(get_current_user)):
    admin = get_user_by_id(current_user["user_id"])
    if not admin or not admin["is_admin"]:
        raise HTTPException(403, "Admin access required")
    if not verify_password(req.admin_password, admin["password_hash"]):
        raise HTTPException(401, "Admin password is incorrect")
    if req.target_user_id == admin["id"]:
        raise HTTPException(400, "Cannot delete yourself")

    target = get_user_by_id(req.target_user_id)
    if not target:
        raise HTTPException(404, "Target user not found")

    if req.action == "delete":
        delete_user(req.target_user_id)
        return {"success": True, "message": f"User '{target['username']}' deleted"}
    elif req.action == "clear_data":
        clear_user_data(req.target_user_id)
        return {"success": True, "message": f"Data cleared for '{target['username']}'"}
    else:
        raise HTTPException(400, "Action must be 'delete' or 'clear_data'")


# ─── Registration settings (admin only) ──────────────────────────
@router.get("/settings")
def get_settings(current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    return {
        "open_registration": get_registration_setting(),
        "is_admin": bool(user["is_admin"]),
    }


@router.post("/settings")
def update_settings(current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user or not user["is_admin"]:
        raise HTTPException(403, "Admin access required")
    from pydantic import BaseModel
    class SettingsRequest(BaseModel):
        open_registration: bool
    # Can't define model inline in function with Pydantic v2
    return {"error": "use POST body"}


@router.post("/settings/registration")
def set_registration(open_registration: bool = True, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user or not user["is_admin"]:
        raise HTTPException(403, "Admin access required")
    set_registration_setting(open_registration)
    audit("registration_policy_changed", user["id"], None, {"open": open_registration})
    return {"success": True, "open_registration": open_registration}


@router.post("/recovery/setup-codes")
def setup_recovery_codes(response: Response, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user or user.get("role") != "owner" or user.get("recovery_setup_complete"):
        raise HTTPException(403, "Recovery setup is not available")
    codes = create_recovery_set(user["id"], "initial_setup", user["id"])
    response.headers["Cache-Control"] = "no-store"
    return {"codes": codes}


@router.post("/recovery/setup-acknowledge")
def acknowledge_recovery_setup(req: RecoveryAckRequest, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user or user.get("role") != "owner" or not req.saved or recovery_status(user["id"])["remaining"] != 12:
        raise HTTPException(400, "Save a complete recovery code set first")
    db = get_users_db()
    try:
        db.execute("UPDATE users SET recovery_setup_complete=1 WHERE id=?", (user["id"],)); db.commit()
    finally: db.close()
    audit("recovery_setup_completed", user["id"], user["id"])
    return {"success": True}


@router.get("/recovery/status")
def get_recovery_status(current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user or user.get("role") != "owner": raise HTTPException(403, "Owner access required")
    return recovery_status(user["id"])


@router.post("/recovery/rotate")
def rotate_recovery(req: RotateRecoveryRequest, response: Response, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user or user.get("role") != "owner": raise HTTPException(403, "Owner access required")
    if not verify_password(req.current_password, user["password_hash"]): raise HTTPException(401, "Current password is incorrect")
    codes = create_recovery_set(user["id"], "manual_rotation", user["id"])
    response.headers["Cache-Control"] = "no-store"
    return {"codes": codes}


@router.post("/recovery/request")
def request_password_reset(req: ForgotPasswordRequest, response: Response, request: Request):
    key = rate_key(request, "recovery-request", req.username); check_rate_limit(key); record_failure(key)
    secret = create_member_reset_request(req.username, request.headers.get("user-agent", ""))
    _set_private_cookie(response, RECOVERY_REQUEST_COOKIE, secret, 24 * 60 * 60)
    return {"message": "If this account exists, a reset request was created."}


@router.get("/recovery/request-status")
def password_reset_status(request: Request):
    secret = request.cookies.get(RECOVERY_REQUEST_COOKIE, "")
    return reset_request_status(secret) if secret else {"status": "pending"}


@router.post("/recovery/member-reset")
def reset_member_password(req: ResetPasswordRequest, response: Response, request: Request):
    if not password_is_supported(req.new_password): raise HTTPException(400, "Password must be between 12 and 72 UTF-8 bytes and must not be commonly used")
    secret = request.cookies.get(RECOVERY_REQUEST_COOKIE, "")
    if not secret or not complete_member_reset(secret, hash_password(req.new_password)): raise HTTPException(400, "Reset approval is invalid or expired")
    response.delete_cookie(RECOVERY_REQUEST_COOKIE, path="/", samesite="strict")
    return {"success": True}


@router.post("/recovery/owner-challenge")
def owner_recovery_challenge(req: OwnerRecoveryRequest, response: Response, request: Request):
    key = rate_key(request, "owner-recovery", req.username); ip_key = rate_key(request, "owner-recovery")
    check_rate_limit(key, ip_key)
    secret = begin_owner_challenge(req.username, req.recovery_code)
    if not secret:
        record_failure(key, ip_key); raise HTTPException(400, "Recovery details are invalid or expired")
    clear_failures(key); _set_private_cookie(response, OWNER_RESET_COOKIE, secret, 15 * 60)
    return {"success": True}


@router.post("/recovery/owner-reset")
def reset_owner_password(req: ResetPasswordRequest, response: Response, request: Request):
    if not password_is_supported(req.new_password, owner=True): raise HTTPException(400, "Owner password must be between 16 and 72 UTF-8 bytes and must not be commonly used")
    secret = request.cookies.get(OWNER_RESET_COOKIE, "")
    result = complete_owner_recovery(secret, hash_password(req.new_password)) if secret else None
    if not result: raise HTTPException(400, "Recovery approval is invalid or expired")
    response.delete_cookie(OWNER_RESET_COOKIE, path="/", samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"success": True, "codes": result[1]}


@router.get("/sessions")
def list_sessions(request: Request, current_user: dict = Depends(get_current_user)):
    current_hash = web_session_binding(request.cookies.get(COOKIE_NAME, "")); now = int(time.time()); db = get_users_db()
    try:
        rows = db.execute("""SELECT DISTINCT s.id_hash,s.created_at,s.last_seen_at,s.expires_at,s.user_agent FROM web_sessions s
          JOIN web_session_accounts a ON a.session_id_hash=s.id_hash WHERE a.user_id=? AND s.expires_at>? ORDER BY s.last_seen_at DESC""", (current_user["user_id"], now)).fetchall()
        return {"sessions": [dict(row) | {"current": row["id_hash"] == current_hash, "id": row["id_hash"][:16]} for row in rows]}
    finally: db.close()


@router.delete("/sessions")
def revoke_other_sessions(request: Request, current_user: dict = Depends(get_current_user)):
    current_hash = web_session_binding(request.cookies.get(COOKIE_NAME, "")); db = get_users_db()
    try:
        rows = db.execute("SELECT session_id_hash FROM web_session_accounts WHERE user_id=? AND session_id_hash<>?", (current_user["user_id"], current_hash)).fetchall()
        db.executemany("DELETE FROM web_sessions WHERE id_hash=?", [(row["session_id_hash"],) for row in rows]); db.commit()
    finally: db.close()
    audit("other_sessions_revoked", current_user["user_id"], current_user["user_id"], {"count": len(rows)})
    return {"success": True, "revoked": len(rows)}


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    db = get_users_db()
    try:
        row = db.execute("SELECT id_hash FROM web_session_accounts WHERE user_id=? AND substr(session_id_hash,1,16)=?", (current_user["user_id"], session_id)).fetchone()
        if not row: raise HTTPException(404, "Session not found")
        db.execute("DELETE FROM web_sessions WHERE id_hash=?", (row["id_hash"],)); db.commit()
    finally: db.close()
    audit("session_revoked", current_user["user_id"], current_user["user_id"])
    return {"success": True, "current": row["id_hash"] == web_session_binding(request.cookies.get(COOKIE_NAME, ""))}
