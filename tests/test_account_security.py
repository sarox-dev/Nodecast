import time
import asyncio
import json

import pytest
from fastapi import HTTPException

from app.services import account_security, auth, database


def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")


def test_recovery_codes_are_hash_only_and_rotation_revokes_old_set(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    owner = database.create_user_in_db("owner", "hash", role="owner")
    first = account_security.create_recovery_set(owner, "initial", owner)
    assert len(first) == 12 and len(set(first)) == 12
    second = account_security.create_recovery_set(owner, "rotation", owner)
    db = database.get_users_db()
    try:
        serialized = b"".join(tmp_path.joinpath("users.db").read_bytes().split())
        assert first[0].encode() not in serialized and second[0].encode() not in serialized
        states = [row["status"] for row in db.execute("SELECT status FROM recovery_code_sets ORDER BY created_at,id")]
        assert states.count("active") == 1 and "revoked" in states
    finally:
        db.close()


def test_owner_recovery_revokes_sessions_and_entire_old_set(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    owner = database.create_user_in_db("owner", "old-hash", role="owner")
    codes = account_security.create_recovery_set(owner, "initial", owner)
    database.create_web_session("session-secret", owner, 3600)
    challenge = account_security.begin_owner_challenge("owner", codes[0])
    result = account_security.complete_owner_recovery(challenge, "new-hash")
    assert result and len(result[1]) == 12
    assert database.get_web_session_user("session-secret") is None
    assert account_security.begin_owner_challenge("owner", codes[1]) is None


def test_member_reset_requires_recent_admin_approval_and_revokes_sessions(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    member = database.create_user_in_db("member", "old-hash", role="member")
    database.create_web_session("session-secret", member, 3600)
    secret = account_security.create_member_reset_request("member", "Test browser")
    assert account_security.reset_request_status(secret)["status"] == "pending"
    db = database.get_users_db()
    try:
        db.execute("UPDATE password_reset_requests SET status='approved',approved_at=?", (int(time.time()),))
        db.commit()
    finally:
        db.close()
    assert account_security.complete_member_reset(secret, "new-hash")
    assert database.get_web_session_user("session-secret") is None
    assert not account_security.complete_member_reset(secret, "another-hash")


def test_nonexistent_member_reset_stays_generic(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    secret = account_security.create_member_reset_request("missing", "Test browser")
    assert account_security.reset_request_status(secret) == {"status": "pending"}


def test_control_roles_cannot_use_member_knowledge_dependencies(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    owner = database.create_user_in_db("owner", "hash", role="owner")
    member = database.create_user_in_db("member", "hash", role="member")
    with pytest.raises(HTTPException) as denied:
        asyncio.run(auth.get_member_user({"user_id": owner}))
    assert denied.value.status_code == 403
    assert asyncio.run(auth.get_member_user({"user_id": member}))["user_id"] == member


def test_locked_ai_policy_resolves_to_owner_configuration(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    owner = database.create_user_in_db("owner", "hash", role="owner")
    member = database.create_user_in_db("member", "hash", role="member")
    database.create_ai_provider(owner, "Shared", "https://api.example/v1")
    database.set_global_setting("ai_policy", json.dumps({"mode": "locked_shared", "shared_owner_user_id": owner, "exceptions": {}}))
    assert database.resolve_ai_config_user(member) == owner
    assert [provider["name"] for provider in database.list_ai_providers(member)] == ["Shared"]


