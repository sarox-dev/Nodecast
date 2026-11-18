import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import auth, account_security, database, setup_security
from app.main import app


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    monkeypatch.setattr(setup_security, "CONTENTS_DIR", tmp_path)
    monkeypatch.setenv("NODECAST_ACCOUNT_MODE", "personal")
    return tmp_path


def test_owner_requires_setup_secret_over_lan(accounts):
    with TestClient(app, base_url="http://192.168.8.116:5000") as client:
        payload = {"username": "owner", "password": "owner-password-long-enough"}
        assert client.post("/auth/register", json=payload).status_code == 403
        assert database.user_count() == 0
        payload["setup_token"] = setup_security.setup_token()
        response = client.post("/auth/register", json=payload)
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "owner"
        assert client.get("/auth/me").status_code == 200


def test_personal_registration_is_atomic(accounts):
    database.create_user_in_db("owner", "hash", role="owner")
    database.set_registration_setting(True)

    def register(index):
        try:
            return database.create_registered_user(f"member-{index}", "hash", owner=False)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(register, range(2)))
    assert sum(result is not None for result in results) == 1
    assert database.member_count() == 1


def test_login_rotation_preserves_accounts_and_revokes_old_secret(accounts):
    owner = database.create_user_in_db("owner", "hash", role="owner")
    member = database.create_user_in_db("member", "hash")
    database.create_web_session("previous", owner, 3600)
    assert database.add_web_session_account("previous", member, 3600)
    assert database.rotate_web_session("previous", "rotated")
    assert database.get_web_session_user("previous") is None
    assert {row["id"] for row in database.list_web_session_accounts("rotated")} == {owner, member}
    assert database.switch_web_session_account("rotated", owner)
    assert database.get_web_session_user("rotated")["id"] == owner


def test_new_reset_does_not_replace_approved_request(accounts):
    member = database.create_user_in_db("member", "hash")
    secret = account_security.create_member_reset_request("member", "legitimate browser")
    db = database.get_users_db()
    db.execute("UPDATE password_reset_requests SET status='approved',approved_at=?", (int(time.time()),))
    db.commit()
    db.close()
    second = account_security.create_member_reset_request("member", "other browser")
    assert account_security.reset_request_status(secret)["status"] == "approved"
    assert account_security.reset_request_status(second)["status"] == "pending"
    assert account_security.complete_member_reset(secret, "new-hash")


def test_active_sessions_include_recent_authenticated_requests(accounts):
    member = database.create_user_in_db("member", "hash")
    assert database.count_active_sessions() == 0
    database.create_web_session("session", member, 3600)
    assert database.count_active_sessions() == 1


def test_malformed_tokens_are_rejected():
    assert auth.decode_token("a" * 17000) is None
    assert auth.decode_token("broken.token.value") is None


def test_lan_and_localhost_cookie_requests_still_work(accounts, monkeypatch):
    monkeypatch.setenv("NODECAST_PUBLIC_ORIGIN", "http://192.168.8.116:5000")
    owner = database.create_user_in_db("owner", auth.hash_password("long-owner-password"), role="owner")
    for origin in ["http://localhost:5000", "http://192.168.8.116:5000", "http://nodecast.lan:5000"]:
        with TestClient(app, base_url=origin) as client:
            response = client.post("/auth/login", headers={"Origin": origin},
                                   json={"username": "owner", "password": "long-owner-password"})
            assert response.status_code == 200
            assert client.get("/auth/me").json()["user_id"] == owner
            assert client.post("/auth/logout", headers={"Origin": origin}).status_code == 200


def test_legacy_markdown_escapes_metadata_and_rejects_script_links():
    from app.services.renderers.markdown import MarkdownRenderer
    renderer = MarkdownRenderer()
    result = renderer.render([{"type": "metadata", "properties": {"<img src=x>": "text"}}],
                             {"source_title": "Title", "source_url": "javascript:alert(1)",
                              "saved_at": "<img src=x>", "captured_at": "<script>bad</script>"})
    assert 'href="javascript:' not in result
    assert "<script>" not in result
    assert "<img src=x>" not in result


def test_snapshot_rejects_non_text_before_writing(accounts, monkeypatch):
    from app.models.capture_package import CapturePackage
    from app.services import raw_storage
    monkeypatch.setattr(raw_storage, "CONTENTS_DIR", accounts)
    with pytest.raises(ValueError, match="must be text"):
        raw_storage.save_raw_capture("member", CapturePackage(), html={"not": "html"})
