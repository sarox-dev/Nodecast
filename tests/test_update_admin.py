import pytest
from fastapi import HTTPException

import app.main as main


def test_version_comparison_is_semantic():
    assert main._version_tuple("1.10.0") > main._version_tuple("1.9.9")
    assert main._version_tuple("v2.0") == (2, 0, 0)


def test_require_admin_accepts_first_admin(monkeypatch):
    monkeypatch.setattr(main, "get_user_by_id", lambda _uid: {"id": "admin", "is_admin": 1})
    assert main.require_admin({"user_id": "admin"})["id"] == "admin"


def test_require_admin_rejects_regular_user(monkeypatch):
    monkeypatch.setattr(main, "get_user_by_id", lambda _uid: {"id": "coder", "is_admin": 0})
    with pytest.raises(HTTPException) as error:
        main.require_admin({"user_id": "coder"})
    assert error.value.status_code == 403
    assert error.value.detail == "Admin access required"


def test_server_settings_report_installation_mode(monkeypatch):
    monkeypatch.setattr("app.services.database.get_global_setting", lambda *_args: "true")
    monkeypatch.setenv("NODECAST_INSTALL_MODE", "host")
    settings = main.get_server_settings({"is_admin": 1})
    assert settings == {"auto_update": True, "installation_mode": "host"}
