import bcrypt
import os
import secrets
from datetime import datetime, timezone, timedelta
import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS
from app.services.database import (
    add_web_session_account, create_web_session, get_user_by_id,
    get_web_session_user, web_session_binding_matches,
)

# ─── Password ─────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


COMMON_WEAK_PASSWORDS = {
    "passwordpassword", "password1234", "123456789012", "qwertyqwerty",
    "letmeinletmein", "adminadminadmin", "correcthorsebatterystaple",
}


def password_is_supported(password: str, *, owner: bool = False) -> bool:
    minimum = 16 if owner else 12
    normalized = "".join(password.casefold().split())
    return minimum <= len(password.encode("utf-8")) <= 72 and normalized not in COMMON_WEAK_PASSWORDS

# ─── JWT ──────────────────────────────────────────────────────────
def create_token(user_id: str, username: str, scope: str = "user", session_binding: str = "") -> str:
    now = datetime.now(timezone.utc)
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User does not exist")
    payload = {
        "sub": user_id,
        "username": username,
        "scope": scope,
        "ver": int(user.get("token_version", 0)),
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    if session_binding:
        payload["sid"] = session_binding
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ─── Dependencies ─────────────────────────────────────────────────
COOKIE_NAME = "nodecast_token"
bearer_scheme = HTTPBearer(auto_error=False)


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="strict",
        max_age=JWT_EXPIRY_HOURS * 3600,
        path="/",
    )

def start_web_session(response, user_id: str, existing_secret: str = "", user_agent: str = "") -> str:
    ttl = JWT_EXPIRY_HOURS * 3600
    if existing_secret and add_web_session_account(existing_secret, user_id, ttl):
        secret = existing_secret
    else:
        secret = secrets.token_urlsafe(48)
        create_web_session(secret, user_id, ttl, user_agent)
    set_session_cookie(response, secret)
    return secret


def _principal(payload: dict | None, allowed_scopes: set[str]) -> dict | None:
    if not payload or payload.get("scope", "user") not in allowed_scopes:
        return None
    user = get_user_by_id(str(payload.get("sub", "")))
    if not user or user.get("disabled") or int(payload.get("ver", -1)) != int(user.get("token_version", 0)):
        return None
    if payload.get("scope") == "extension" and payload.get("sid") and not web_session_binding_matches(payload["sid"], user["id"]):
        return None
    return {"user_id": user["id"], "username": user["username"], "scope": payload.get("scope", "user")}

async def get_user_from_cookie(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user = get_web_session_user(token)
    if user:
        return {"user_id": user["id"], "username": user["username"], "scope": "user", "session_secret": token}
    return _principal(decode_token(token), {"user"})

async def get_user_from_bearer(credentials: HTTPAuthorizationCredentials | None, allowed_scopes: set[str] | None = None) -> dict | None:
    if credentials is None:
        return None
    return _principal(decode_token(credentials.credentials), allowed_scopes or {"user"})

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    # An explicit Authorization header must never silently fall back to a
    # browser cookie.  This keeps token-authenticated API clients separate
    # from the ambient web session.
    if credentials is not None:
        user = await get_user_from_bearer(credentials)
        if user:
            return user
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await get_user_from_cookie(request)
    if user:
        return user
    raise HTTPException(status_code=401, detail="Not authenticated")


async def get_member_user(current_user: dict = Depends(get_current_user)) -> dict:
    account = get_user_by_id(current_user["user_id"])
    if not account or account.get("role") != "member" or account.get("disabled"):
        raise HTTPException(status_code=403, detail="A member account is required")
    return current_user


async def get_capture_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if credentials is not None:
        user = await get_user_from_bearer(credentials, {"user", "extension"})
        if user:
            account = get_user_by_id(user["user_id"])
            if account and account.get("role") == "member" and not account.get("disabled"):
                return user
            raise HTTPException(status_code=403, detail="A member account is required")
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await get_user_from_cookie(request)
    if user:
        account = get_user_by_id(user["user_id"])
        if account and account.get("role") == "member" and not account.get("disabled"):
            return user
        raise HTTPException(status_code=403, detail="A member account is required")
    raise HTTPException(status_code=401, detail="Not authenticated")

async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    if credentials is not None:
        return await get_user_from_bearer(credentials)
    user = await get_user_from_cookie(request)
    if user:
        return user
    return None
