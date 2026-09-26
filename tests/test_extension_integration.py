import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import extension


USER = {"user_id": "user-1", "username": "coder"}


def test_pairing_code_is_single_use(monkeypatch):
    monkeypatch.setattr(extension, "create_token", lambda user_id, username: f"token:{user_id}:{username}")
    created = extension.create_pairing_code(USER)

    first = extension.exchange_pairing_code(extension.PairingExchange(code=created["code"]))
    assert first == {"token": "token:user-1:coder", "user_id": "user-1", "username": "coder"}

    with pytest.raises(HTTPException) as error:
        extension.exchange_pairing_code(extension.PairingExchange(code=created["code"]))
    assert error.value.status_code == 401


def test_extension_settings_are_bounded():
    with pytest.raises(ValidationError):
        extension.ExtensionSettings(min_selection_length=0)
    with pytest.raises(ValidationError):
        extension.ExtensionSettings(min_selection_length=501)


def test_extension_settings_round_trip(monkeypatch):
    stored = {}
    monkeypatch.setattr(extension, "set_user_setting", lambda uid, key, value: stored.update({(uid, key): value}))
    monkeypatch.setattr(extension, "get_user_setting", lambda uid, key, default: stored.get((uid, key), default))
    requested = extension.ExtensionSettings(
        floating_button_enabled=False,
        min_selection_length=24,
        notification_position="bottom-right",
        default_project="Recipes",
    )

    saved = extension.update_extension_settings(requested, USER)
    loaded = extension.get_extension_settings(USER)

    assert saved["success"] is True
    assert loaded["settings"] == requested.model_dump()
