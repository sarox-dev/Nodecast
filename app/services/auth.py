import bcrypt
import os
from datetime import datetime, timezone, timedelta
import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS
from app.services.database import get_user_by_id

# ─── Password ─────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def password_is_supported(password: str) -> bool:
    return 12 <= len(password.encode("utf-8")) <= 72

# ─── JWT ──────────────────────────────────────────────────────────
def create_token(user_id: str, username: str, scope: str = "user") -> str:
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


def _principal(payload: dict | None, allowed_scopes: set[str]) -> dict | None:
    if not payload or payload.get("scope", "user") not in allowed_scopes:
        return None
    user = get_user_by_id(str(payload.get("sub", "")))
    if not user or int(payload.get("ver", -1)) != int(user.get("token_version", 0)):
        return None
    return {"user_id": user["id"], "username": user["username"], "scope": payload.get("scope", "user")}

async def get_user_from_cookie(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return _principal(decode_token(token), {"user"})

async def get_user_from_bearer(credentials: HTTPAuthorizationCredentials | None, allowed_scopes: set[str] | None = None) -> dict | None:
    if credentials is None:
        return None
    return _principal(decode_token(credentials.credentials), allowed_scopes or {"user"})

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    # Try cookie first (Web UI), then Bearer (Extension/API)
    user = await get_user_from_cookie(request)
    if user:
        return user
    user = await get_user_from_bearer(credentials)
    if user:
        return user
    raise HTTPException(status_code=401, detail="Not authenticated")


async def get_capture_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    user = await get_user_from_cookie(request)
    if user:
        return user
    user = await get_user_from_bearer(credentials, {"user", "extension"})
    if user:
        return user
    raise HTTPException(status_code=401, detail="Not authenticated")

async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    user = await get_user_from_cookie(request)
    if user:
        return user
    return await get_user_from_bearer(credentials)
