from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel

from app.services.auth import (
    hash_password, verify_password, create_token,
    get_current_user, COOKIE_NAME
)
from app.services.database import (
    init_user_db, user_exists,
    create_user_in_db, get_user_by_username, get_user_by_id,
    get_all_users, update_password, update_username,
    delete_user, clear_user_data,
    user_count, get_registration_setting, set_registration_setting,
)

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


# ─── Check ───────────────────────────────────────────────────────
@router.get("/check")
def check_users():
    return {"has_users": user_count() > 0}


# ─── Register ─────────────────────────────────────────────────────
@router.post("/register")
def register(req: RegisterRequest, response: Response):
    username = req.username.strip().lower()
    if not username or len(username) < 2:
        raise HTTPException(400, "Username must be at least 2 characters")
    if not req.password or len(req.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")

    if user_exists(username):
        raise HTTPException(409, "Username already exists")

    # First user is admin
    is_admin = user_count() == 0

    # Check if registration is open
    if not is_admin and not get_registration_setting():
        raise HTTPException(403, "Registration is closed. Contact your admin.")

    user_id = create_user_in_db(username, hash_password(req.password), is_admin=is_admin)
    init_user_db(user_id)

    token = create_token(user_id, username)
    response.set_cookie(
        key=COOKIE_NAME, value=token,
        httponly=True, samesite="lax", max_age=72 * 3600
    )
    return {
        "success": True,
        "user": {"user_id": user_id, "username": username, "is_admin": is_admin},
        "token": token,
    }


# ─── Login ────────────────────────────────────────────────────────
@router.post("/login")
def login(req: LoginRequest, response: Response):
    username = req.username.strip().lower()
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(401, "Invalid username or password")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid username or password")

    token = create_token(user["id"], username)
    response.set_cookie(
        key=COOKIE_NAME, value=token,
        httponly=True, samesite="lax", max_age=72 * 3600
    )
    return {
        "success": True,
        "user": {"user_id": user["id"], "username": username, "is_admin": bool(user["is_admin"])},
        "token": token,
    }


# ─── Logout ──────────────────────────────────────────────────────
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"success": True, "message": "Logged out"}


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
        "created_at": user["created_at"],
    }


# ─── Get current token ────────────────────────────────────────────
@router.get("/token")
def get_token(current_user: dict = Depends(get_current_user)):
    token = create_token(current_user["user_id"], current_user["username"])
    return {"token": token}


# ─── Change password ─────────────────────────────────────────────
@router.post("/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(401, "Current password is incorrect")
    if len(req.new_password) < 4:
        raise HTTPException(400, "New password must be at least 4 characters")
    update_password(user["id"], hash_password(req.new_password))
    return {"success": True, "message": "Password updated"}


# ─── Change username ─────────────────────────────────────────────
@router.post("/change-username")
def change_username(req: ChangeUsernameRequest, current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Password is incorrect")
    new_username = req.new_username.strip().lower()
    if not new_username or len(new_username) < 2:
        raise HTTPException(400, "Username must be at least 2 characters")
    if new_username != user["username"] and user_exists(new_username):
        raise HTTPException(409, "Username already taken")
    update_username(user["id"], new_username)
    # Generate new token with new username
    token = create_token(user["id"], new_username)
    return {"success": True, "message": "Username updated", "token": token}


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
    return {"success": True, "open_registration": open_registration}