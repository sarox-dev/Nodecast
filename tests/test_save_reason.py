import json
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from app.services import database, save_reason
from app.api.routes import capture


def setup_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    uid = database.create_user_in_db("reason-user", "hash")
    cid = "test_capture_001"
    database.insert_capture_ref(uid, cid, "snippet", "https://example.org", "Example title", "example.org", "", "2026-11-06T00:00:00Z", [], "", "")
    database.set_user_setting(uid, "save_reason_ai_enabled", "true")
    monkeypatch.setattr(save_reason, "get_ai_assignment_for_feature", lambda *_: {"provider_id": "p", "model": "m"})
    monkeypatch.setattr(save_reason, "get_ai_provider", lambda *_: {"id": "p"})
    monkeypatch.setattr(save_reason, "load_raw_capture", lambda *_: SimpleNamespace(anchor=SimpleNamespace(selected_text="Selected text")))
    return uid, cid


def test_inference_only_uses_current_capture_and_keeps_suggestion_unconfirmed(tmp_path, monkeypatch):
    uid, cid = setup_capture(tmp_path, monkeypatch)
    calls = []
    def provider(_uid, _provider, _model, messages, **_kwargs):
        calls.append(messages)
        return json.dumps({"category": "try_later", "suggestion": "Possibly try later"})
    monkeypatch.setattr(save_reason, "call_provider_model", provider)
    assert save_reason.infer_save_reason(uid, cid)["status"] == "success"
    assert json.loads(calls[0][1]["content"]) == {"title": "Example title", "excerpt": "Selected text"}
    result = database.get_capture_ref(uid, cid)
    assert result["save_reason"] == "" and result["save_reason_status"] == "unknown"
    assert result["save_reason_suggestion"] == "Possibly try later"


def test_late_inference_cannot_overwrite_user_decline(tmp_path, monkeypatch):
    uid, cid = setup_capture(tmp_path, monkeypatch)
    def provider(*_args, **_kwargs):
        database.set_capture_save_reason(uid, cid, "", "declined")
        return json.dumps({"category": "try_later", "suggestion": "Try later"})
    monkeypatch.setattr(save_reason, "call_provider_model", provider)
    save_reason.infer_save_reason(uid, cid)
    result = database.get_capture_ref(uid, cid)
    assert result["save_reason_status"] == "declined"
    assert result["save_reason_suggestion"] == ""


def test_inference_disabled_and_invalid_output(tmp_path, monkeypatch):
    uid, cid = setup_capture(tmp_path, monkeypatch)
    database.set_user_setting(uid, "save_reason_ai_enabled", "false")
    monkeypatch.setattr(save_reason, "call_provider_model", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not call AI")))
    assert save_reason.infer_save_reason(uid, cid)["status"] == "skipped"
    database.set_user_setting(uid, "save_reason_ai_enabled", "true")
    monkeypatch.setattr(save_reason, "call_provider_model", lambda *_args, **_kwargs: '{"category":"invented","suggestion":"x"}')
    assert save_reason.infer_save_reason(uid, cid)["status"] == "error"
    assert database.get_capture_ref(uid, cid)["save_reason_inferred_at"] == ""


def test_review_expires_without_recording_a_decline(tmp_path, monkeypatch):
    uid, cid = setup_capture(tmp_path, monkeypatch)
    recent = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    connection = database.get_db(uid)
    try:
        connection.execute("UPDATE captures SET saved_at=?,save_reason_inferred_at=?,save_reason_category='unknown' WHERE id=?", (recent, recent, cid))
        connection.commit()
    finally:
        connection.close()
    assert [x["id"] for x in capture.list_reason_review({"user_id": uid})["items"]] == [cid]
    connection = database.get_db(uid)
    try:
        connection.execute("UPDATE captures SET saved_at=? WHERE id=?", (old, cid))
        connection.commit()
    finally:
        connection.close()
    assert capture.list_reason_review({"user_id": uid})["items"] == []
    assert database.get_capture_ref(uid, cid)["save_reason_status"] == "unknown"


def test_capture_saves_optional_reason_with_capture_and_defaults_ai_on(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    uid = database.create_user_in_db("reason-create", "hash")
    saved = []
    monkeypatch.setattr(capture, "save_raw_capture", lambda _uid, package, html=None: saved.append(package.model_dump()) or tmp_path)
    monkeypatch.setattr(capture, "get_ai_assignment_for_feature", lambda *_: None)
    response = capture.capture_item({"capture_id":"capture_new_001", "source":{"title":"Example"}, "save_reason":" Compare tools "}, {"user_id":uid})
    assert response.success
    record = database.get_capture_ref(uid, "capture_new_001")
    assert (record["save_reason"], record["save_reason_status"]) == ("Compare tools", "confirmed")
    assert "save_reason" not in saved[0]
    assert capture.get_reason_settings({"user_id":uid})["ai_enabled"] is True


def test_new_reasonless_captures_queue_ai_by_default_but_respect_explicit_disable(tmp_path, monkeypatch):
    from app.services import ai_batch
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    uid = database.create_user_in_db("reason-default", "hash")
    monkeypatch.setattr(capture, "save_raw_capture", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(capture, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p"})
    monkeypatch.setattr(capture, "get_ai_provider", lambda *_: {"id":"p"})
    jobs = []
    monkeypatch.setattr(capture, "add_ai_job", lambda _u, cid, feature: jobs.append((cid,feature)))
    monkeypatch.setattr(ai_batch, "start_background_batch", lambda *_args: None)
    capture.capture_item({"capture_id":"capture_new_001"}, {"user_id":uid})
    assert jobs == [("capture_new_001", "save_reason_inference")]
    capture.capture_item({"capture_id":"capture_new_002", "save_reason":"A reason"}, {"user_id":uid})
    database.set_user_setting(uid, "save_reason_ai_enabled", "false")
    capture.capture_item({"capture_id":"capture_new_003"}, {"user_id":uid})
    assert len(jobs) == 1


