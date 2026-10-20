"""Sign in with ChatGPT for local/open-source Nodecast installations."""

import base64
import hashlib
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.error import URLError

import httpx
import jwt

from app.services.ai_crypto import decrypt_api_key
from app.services.database import (
    create_ai_oauth_transaction,
    get_ai_oauth_credentials,
    get_global_setting,
    save_ai_oauth_credentials,
    set_global_setting,
)


AUTHORIZATION_ENDPOINT = "https://auth.openai.com/api/accounts/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/api/accounts/oauth/token"
JWKS_ENDPOINT = "https://auth.openai.com/.well-known/jwks.json"
ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
_refresh_locks: dict[str, threading.Lock] = {}
_refresh_locks_guard = threading.Lock()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def get_or_create_host_id() -> str:
    host_id = get_global_setting("chatgpt_oauth_host_id", "")
    if not host_id:
        host_id = f"urn:uuid:{uuid.uuid4()}"
        set_global_setting("chatgpt_oauth_host_id", host_id)
    return host_id


def begin_authorization(user_id: str, redirect_uri: str) -> str:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    create_ai_oauth_transaction(state, user_id, verifier, nonce, redirect_uri)
    params = {
        "response_type": "code",
        "client_id": "dynamic_agent_client",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "ext_agent_host_id": get_or_create_host_id(),
        "agent_name_hint": "Nodecast",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


def exchange_code(transaction: dict, code: str, client_id: str) -> tuple[dict, dict]:
    with httpx.Client(timeout=30) as client:
        response = client.post(TOKEN_ENDPOINT, data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": transaction["code_verifier"],
            "redirect_uri": transaction["redirect_uri"],
            "resource": RESOURCE,
        })
        response.raise_for_status()
        tokens = response.json()
    granted_scopes = set(str(tokens.get("scope", "")).split())
    if "chatgpt.tokens.use.direct" not in granted_scopes:
        raise ValueError("ChatGPT plan usage permission was not granted")
    id_token = tokens.get("id_token", "")
    if not id_token:
        raise ValueError("OpenAI did not return an ID token")
    try:
        signing_key = jwt.PyJWKClient(JWKS_ENDPOINT).get_signing_key_from_jwt(id_token)
        identity = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=client_id,
            issuer=ISSUER,
        )
    except (jwt.PyJWTError, URLError) as exc:
        raise ValueError("OpenAI identity token validation failed") from exc
    if identity.get("nonce") != transaction["nonce"]:
        raise ValueError("Invalid OAuth nonce")
    return tokens, identity


def store_tokens(user_id: str, provider_id: str, client_id: str, tokens: dict, identity: dict) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(tokens.get("expires_in", 0)) - 60))
    save_ai_oauth_credentials(
        user_id, provider_id, client_id, tokens["access_token"], tokens.get("refresh_token", ""),
        tokens.get("id_token", ""), expires_at.isoformat(), str(identity.get("sub", "")),
        str(identity.get("email", "")), str(tokens.get("scope", SCOPES)),
    )


def _lock_for(provider_id: str) -> threading.Lock:
    with _refresh_locks_guard:
        return _refresh_locks.setdefault(provider_id, threading.Lock())


def get_access_token(user_id: str, provider_id: str) -> str:
    with _lock_for(provider_id):
        credentials = get_ai_oauth_credentials(user_id, provider_id)
        if not credentials:
            raise ValueError("ChatGPT is not connected")
        access_token = decrypt_api_key(credentials["access_token_encrypted"])
        try:
            expires_at = datetime.fromisoformat(credentials.get("expires_at") or "")
        except ValueError:
            expires_at = datetime.min.replace(tzinfo=timezone.utc)
        if access_token and expires_at > datetime.now(timezone.utc):
            return access_token
        refresh_token = decrypt_api_key(credentials.get("refresh_token_encrypted", ""))
        if not refresh_token:
            raise ValueError("ChatGPT authorization expired; reconnect the account")
        with httpx.Client(timeout=30) as client:
            response = client.post(TOKEN_ENDPOINT, data={
                "grant_type": "refresh_token",
                "client_id": credentials["client_id"],
                "refresh_token": refresh_token,
                "resource": RESOURCE,
            })
            response.raise_for_status()
            tokens = response.json()
        identity = {
            "sub": credentials.get("account_id", ""),
            "email": credentials.get("account_email", ""),
        }
        if not tokens.get("refresh_token"):
            tokens["refresh_token"] = refresh_token
        if not tokens.get("id_token"):
            tokens["id_token"] = decrypt_api_key(credentials.get("id_token_encrypted", ""))
        store_tokens(user_id, provider_id, credentials["client_id"], tokens, identity)
        return tokens["access_token"]

