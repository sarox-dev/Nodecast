import pytest
from fastapi import HTTPException

from app.api.routes import admin
import app.main as main
from app.services import database


def test_legacy_installations_default_to_shared(monkeypatch):
    monkeypatch.delenv("NODECAST_ACCOUNT_MODE", raising=False)
    assert database.get_account_mode() == "shared"


def test_personal_mode_rejects_a_second_library_member(monkeypatch):
    monkeypatch.setattr(admin, "_actor", lambda _user: {"id": "owner", "role": "owner"})
    monkeypatch.setattr(admin, "get_account_mode", lambda: "personal")
    monkeypatch.setattr(admin, "member_count", lambda: 1)

    with pytest.raises(HTTPException) as error:
        admin.create_account(
            admin.CreateAccountRequest(username="another", password="long-enough-password"),
            {"user_id": "owner"},
        )

    assert error.value.status_code == 409


def test_shared_mode_does_not_apply_personal_member_limit(monkeypatch):
    monkeypatch.setattr(admin, "_actor", lambda _user: {"id": "owner", "role": "owner"})
    monkeypatch.setattr(admin, "get_account_mode", lambda: "shared")
    monkeypatch.setattr(admin, "member_count", lambda: 5)
    monkeypatch.setattr(admin, "password_is_supported", lambda _password: True)
    monkeypatch.setattr(admin, "get_users_db", lambda: _EmptyUsersDb())
    monkeypatch.setattr(admin, "create_user_in_db", lambda *_args, **_kwargs: "new-member")
    monkeypatch.setattr(admin, "init_user_db", lambda _uid: None)
    monkeypatch.setattr(admin, "audit", lambda *_args, **_kwargs: None)

    result = admin.create_account(
        admin.CreateAccountRequest(username="another", password="long-enough-password"),
        {"user_id": "owner"},
    )

    assert result == {"success": True, "user_id": "new-member"}


class _EmptyUsersDb:
    def execute(self, *_args):
        return self

    def fetchone(self):
        return None

    def close(self):
        pass


def test_personal_mode_startup_rejects_existing_multi_member_install(monkeypatch):
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(database, "get_account_mode", lambda: "personal")
    monkeypatch.setattr(database, "member_count", lambda: 2)

    with pytest.raises(RuntimeError, match="more than one Library member"):
        main.startup()
