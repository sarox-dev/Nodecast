import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app
from app.services import auth, auth_rate_limit, database


@pytest.fixture(autouse=True)
def isolated_limits():
    auth_rate_limit._attempts.clear()
    yield
    auth_rate_limit._attempts.clear()


def test_sensitive_account_routes_share_one_password_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    monkeypatch.setattr(auth, "verify_password", lambda *_: False)
    owner = database.create_user_in_db("owner", "hash", role="owner")
    member = database.create_user_in_db("member", "hash", role="member")
    database.create_web_session("browser-secret", owner, 3600)
    client = TestClient(app)
    client.cookies.set(auth.COOKIE_NAME, "browser-secret")
    actions = [
        ("/auth/change-password", {"current_password": "wrong", "new_password": "long-new-password"}),
        ("/auth/change-username", {"password": "wrong", "new_username": "new-owner"}),
        ("/auth/recovery/rotate", {"current_password": "wrong"}),
        ("/auth/admin/user", {"admin_password": "wrong", "target_user_id": member, "action": "clear_data"}),
        (f"/api/admin/users/{member}/action", {"current_password": "wrong", "action": "disable"}),
    ]
    for index in range(auth_rate_limit.MAX_ATTEMPTS):
        path, payload = actions[index % len(actions)]
        assert client.post(path, json=payload).status_code == 401
    for path, payload in actions:
        assert client.post(path, json=payload).status_code == 429
    assert not database.get_user_by_id(member)["disabled"]


def test_successful_reauthentication_resets_failure_budget(monkeypatch):
    request = Request({"type": "http", "headers": [], "client": ("192.168.8.5", 1234)})
    account = {"id": "member", "password_hash": "hash"}
    monkeypatch.setattr(auth, "verify_password", lambda password, _hash: password == "correct")
    for _ in range(auth_rate_limit.MAX_ATTEMPTS - 1):
        assert not auth.verify_account_password(request, account, "wrong")
    assert auth.verify_account_password(request, account, "correct")
    for _ in range(auth_rate_limit.MAX_ATTEMPTS):
        assert not auth.verify_account_password(request, account, "wrong")
    with pytest.raises(HTTPException) as limited:
        auth.verify_account_password(request, account, "wrong")
    assert limited.value.status_code == 429


def test_changing_recovery_username_does_not_bypass_client_limit(monkeypatch):
    from app.api.routes import auth as routes
    monkeypatch.setattr(routes, "create_member_reset_request", lambda *_: "temporary-secret")
    client = TestClient(app)
    for index in range(auth_rate_limit.MAX_ATTEMPTS):
        assert client.post("/auth/recovery/request", json={"username": f"member-{index}"}).status_code == 200
    assert client.post("/auth/recovery/request", json={"username": "another"}).status_code == 429

def test_correct_password_keeps_normal_account_actions_working(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    password = "long-owner-password"
    owner = database.create_user_in_db("owner", auth.hash_password(password), role="owner")
    member = database.create_user_in_db("member", "hash", role="member")
    database.create_web_session("browser-secret", owner, 3600)
    client = TestClient(app)
    client.cookies.set(auth.COOKIE_NAME, "browser-secret")
    rotated = client.post("/auth/recovery/rotate", json={"current_password": password})
    assert rotated.status_code == 200 and len(rotated.json()["codes"]) == 12
    changed = client.post(f"/api/admin/users/{member}/action",
                          json={"current_password": password, "action": "disable"})
    assert changed.status_code == 200 and database.get_user_by_id(member)["disabled"]
    cleared = client.post("/auth/admin/user", json={
        "admin_password": password, "target_user_id": member, "action": "clear_data",
    })
    assert cleared.status_code == 200
    renamed = client.post("/auth/change-username", json={"password": password, "new_username": "new-owner"})
    assert renamed.status_code == 200
    changed_password = client.post("/auth/change-password", json={
        "current_password": password, "new_password": "another-long-owner-password",
    })
    assert changed_password.status_code == 200
    assert client.get("/auth/me").json()["username"] == "new-owner"
