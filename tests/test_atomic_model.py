import sqlite3

from app.services import database


def _user_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CONTENTS_DIR", tmp_path)
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    user_id = database.create_user_in_db("tester", "hash", True)
    database.init_user_db(user_id)
    return user_id


def test_fresh_schema_contains_only_atomic_knowledge_tables(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    conn = database.get_db(user_id)
    try:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"captures", "atomics", "atomic_relations"} <= tables
    assert not {"knowledge_objects", "entities", "capture_entities", "facts", "relations", "capture_ai_tags"} & tables


def test_atomic_relations_reject_capture_ids(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "capture-1", "snippet", "https://example.com", "Example", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "text", "A fact", source_id="capture-1")
    try:
        database.insert_atomic_relation(user_id, atomic_id, "capture-1", "source_of")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("atomic_relations accepted a capture id")


def test_deleting_capture_cascades_to_atomics(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "capture-1", "snippet", "https://example.com", "Example", "example.com", "", "", [], "", "")
    database.insert_atomic(user_id, "text", "A fact", source_id="capture-1")
    assert database.delete_capture_ref(user_id, "capture-1")
    assert database.get_atomics_by_source(user_id, "capture-1") == []
