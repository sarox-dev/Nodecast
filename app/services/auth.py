import bcrypt
from datetime import datetime, timezone, timedelta
import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS

# ─── Password ─────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

# ─── JWT ──────────────────────────────────────────────────────────
def create_token(user_id: str, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
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
COOKIE_NAME = "recollect_token"
bearer_scheme = HTTPBearer(auto_error=False)

async def get_user_from_cookie(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    return {"user_id": payload["sub"], "username": payload["username"]}

async def get_user_from_bearer(credentials: HTTPAuthorizationCredentials | None) -> dict | None:
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if payload is None:
        return None
    return {"user_id": payload["sub"], "username": payload["username"]}

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

async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    user = await get_user_from_cookie(request)
    if user:
        return user
    return await get_user_from_bearer(credentials)