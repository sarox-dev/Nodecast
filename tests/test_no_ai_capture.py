"""Exercise save, indexing, recovery and source lookup with no configured AI."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai_batch, atomic_extraction, auto_processor, database, raw_storage
from app.services.auth import hash_password

TEXT = "SQLite WAL checkpoint moves committed frames back into the main database file."
HTML = f"<main><h1>SQLite WAL</h1><p>{TEXT}</p><p>Readers can continue using a consistent snapshot while other connections write.</p></main>"
PASSWORD = "Synthetic-test-passphrase-29"


@pytest.fixture
def account(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CONTENTS_DIR", tmp_path)
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    monkeypatch.setattr(raw_storage, "CONTENTS_DIR", tmp_path)
    uid = database.create_user_in_db("no-ai-member", hash_password(PASSWORD))
    database.init_user_db(uid)
    monkeypatch.setattr(atomic_extraction, "call_provider_model", lambda *_a, **_kw: pytest.fail("AI must not be called"))
    monkeypatch.setattr(ai_batch, "start_background_batch", lambda user_id, operation="atomic_extraction": ai_batch.process_batch(user_id, operation))
    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "no-ai-member", "password": PASSWORD}).status_code == 200
    yield uid, client, tmp_path
    client.close()
    ai_batch._status.pop(uid, None)


def package(cid, *, html=False, selection=True):
    body = {"capture_id": cid, "capture_type": "snippet" if selection else "page",
            "source": {"url": "https://example.test/sqlite", "title": "SQLite WAL guide"}}
    if selection:
        body["anchor"] = {"selected_text": TEXT}
    if html:
        body["page_html"] = HTML
    return body


@pytest.mark.parametrize("html,selection", [(False, True), (True, True), (True, False)])
def test_authenticated_save_find_and_original_without_ai(account, html, selection):
    uid, client, root = account
    cid = "capture_no_ai_001"
    assert database.list_ai_providers(uid) == []
    response = client.post("/api/capture", json=package(cid, html=html, selection=selection))
    assert response.status_code == 200 and response.json()["success"]
    raw = root / "users" / uid / "raw" / cid / "capture.json"
    original_bytes = raw.read_bytes()
    indexed = database.get_atomics_by_source(uid, cid)
    assert indexed and all(row["source_id"] == cid for row in indexed)
    found = client.post("/api/memory/query", json={"query": "SQLite WAL checkpoint", "mode": "fast", "synthesize": False})
    assert found.status_code == 200
    assert any(item["source_id"] == cid for item in found.json()["items"])
    assert found.json()["synthesis_status"] == "local_only"
    source = client.get(f"/api/capture/{cid}")
    assert source.status_code == 200
    assert source.json()["capture"]["source"]["url"] == "https://example.test/sqlite"
    if selection:
        assert source.json()["capture"]["anchor"]["selected_text"] == TEXT
    assert raw.read_bytes() == original_bytes
    stranger = TestClient(app)
    other = database.create_user_in_db("other-member", hash_password(PASSWORD))
    assert stranger.post("/auth/login", json={"username": "other-member", "password": PASSWORD}).status_code == 200
    assert stranger.get(f"/api/capture/{cid}").status_code == 404
    assert stranger.post("/api/memory/query", json={"query": "SQLite WAL checkpoint", "mode": "fast", "synthesize": False}).json()["items"] == []
    stranger.close()


def test_metadata_only_save_does_not_claim_indexing(account):
    uid, client, _root = account
    response = client.post("/api/capture", json=package("capture_empty_001", selection=False))
    assert response.status_code == 200
    assert "not indexed" in response.json()["message"]
    assert database.get_atomics_by_source(uid, "capture_empty_001") == []
    assert database.count_pending_ai_jobs(uid) == 0


def test_reextract_text_only_capture_requeues_completed_job_without_changing_raw(account):
    uid, client, root = account
    cid = "capture_retry_001"
    assert client.post("/api/capture", json=package(cid)).status_code == 200
    raw = root / "users" / uid / "raw" / cid / "capture.json"
    before = raw.read_bytes()
    assert client.post(f"/api/capture/{cid}/reextract").status_code == 200
    assert database.get_atomics_by_source(uid, cid)
    assert raw.read_bytes() == before


@pytest.mark.parametrize("html,selection", [(False, True), (True, False)])
def test_scheduler_recovers_previously_unindexed_sources(account, monkeypatch, html, selection):
    uid, client, root = account
    cid = "capture_legacy_001"
    # Preserve the raw capture but emulate the old completed/skipped processor job.
    monkeypatch.setattr(ai_batch, "start_background_batch", lambda *_a, **_kw: None)
    assert client.post("/api/capture", json=package(cid, html=html, selection=selection)).status_code == 200
    raw = root / "users" / uid / "raw" / cid / "capture.json"
    before = raw.read_bytes()
    connection = database.get_db(uid)
    try:
        connection.execute("DELETE FROM pending_ai_jobs")
        connection.commit()
    finally:
        connection.close()
    old = database.add_ai_job(uid, cid, "atomic_extraction", processor_version="1")
    database.mark_ai_job_done(uid, old["id"])
    monkeypatch.setattr(ai_batch, "start_background_batch", lambda user_id, *_a: ai_batch.process_batch(user_id))
    monkeypatch.setattr(auto_processor, "_processor_thread", SimpleNamespace())
    auto_processor._process_for_user(uid)
    assert database.get_atomics_by_source(uid, cid)
    assert raw.read_bytes() == before
    assert database.list_captures_without_ai_data(uid) == []


def test_upgrade_reuses_active_legacy_job(account):
    uid, _client, _root = account
    cid = "capture_pending_001"
    database.insert_capture_ref(uid, cid, "snippet", "", "", "", "", "", [], "", "")
    old = database.add_ai_job(uid, cid, "atomic_extraction", processor_version="1")
    assert ai_batch.queue_atomic_extraction(uid, cid)["id"] == old["id"]
    connection = database.get_db(uid)
    try:
        assert connection.execute("SELECT COUNT(*) FROM pending_ai_jobs WHERE capture_id=?", (cid,)).fetchone()[0] == 1
    finally:
        connection.close()
