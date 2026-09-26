import json
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.auth import create_token, get_current_user
from app.services.database import get_user_setting, set_user_setting


router = APIRouter(prefix="/api/extension", tags=["extension"])

PAIRING_TTL_SECONDS = 90
_pairing_codes: dict[str, dict] = {}
_pairing_lock = threading.Lock()


class PairingExchange(BaseModel):
    code: str = Field(min_length=16, max_length=200)


class ExtensionSettings(BaseModel):
    floating_button_enabled: bool = True
    min_selection_length: int = Field(default=10, ge=1, le=500)
    notification_position: str = "top-center"
    default_project: str = Field(default="", max_length=200)


def _clean_pairing_codes(now: float) -> None:
    expired = [code for code, item in _pairing_codes.items() if item["expires_at"] <= now]
    for code in expired:
        _pairing_codes.pop(code, None)


def _load_settings(user_id: str) -> ExtensionSettings:
    raw = get_user_setting(user_id, "extension_settings", "")
    if not raw:
        return ExtensionSettings()
    try:
        return ExtensionSettings(**json.loads(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return ExtensionSettings()


@router.post("/pairing-code")
def create_pairing_code(current_user: dict = Depends(get_current_user)):
    now = time.time()
    code = secrets.token_urlsafe(24)
    with _pairing_lock:
        _clean_pairing_codes(now)
        _pairing_codes[code] = {
            "user_id": current_user["user_id"],
            "username": current_user["username"],
            "expires_at": now + PAIRING_TTL_SECONDS,
        }
    return {"code": code, "expires_in": PAIRING_TTL_SECONDS}


@router.post("/exchange")
def exchange_pairing_code(request: PairingExchange):
    now = time.time()
    with _pairing_lock:
        _clean_pairing_codes(now)
        pairing = _pairing_codes.pop(request.code, None)
    if not pairing:
        raise HTTPException(401, "Pairing code is invalid or expired")
    token = create_token(pairing["user_id"], pairing["username"])
    return {
        "token": token,
        "user_id": pairing["user_id"],
        "username": pairing["username"],
    }


@router.get("/settings")
def get_extension_settings(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "settings": _load_settings(current_user["user_id"]).model_dump(),
    }


@router.put("/settings")
def update_extension_settings(
    settings: ExtensionSettings,
    current_user: dict = Depends(get_current_user),
):
    if settings.notification_position not in {
        "top-left", "top-center", "top-right",
        "bottom-left", "bottom-center", "bottom-right",
    }:
        raise HTTPException(422, "Unsupported notification position")
    payload = settings.model_dump()
    set_user_setting(current_user["user_id"], "extension_settings", json.dumps(payload))
    return {"success": True, "settings": payload}
