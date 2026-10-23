import unicodedata

from app.services import database
from app.services.text_analysis import ANALYZER_VERSION, analyze_text


def _user_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CONTENTS_DIR", tmp_path)
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    user_id = database.create_user_in_db("unicode-tester", "hash", False)
    database.init_user_db(user_id)
    return user_id


def test_analyzer_normalizes_unicode_and_preserves_script_runs():
    decomposed = "Ri\u0304ga SQLite预写式日志 اختبار"
    result = analyze_text(decomposed)

    assert result.normalized_text == unicodedata.normalize("NFC", decomposed).casefold()
    assert {span.script for span in result.scripts} >= {"Latin", "Han", "Arabic"}
    assert any(term.startswith("zhan2") for term in result.lexical_terms)


def test_analyzer_protects_technical_identifiers_and_is_deterministic():
    first = analyze_text("GatewayTimeoutError E504 upstream_server llama.cpp", mode="query")
    second = analyze_text("GatewayTimeoutError E504 upstream_server llama.cpp", mode="query")

    assert first == second
    assert len(first.protected_terms) >= 3
    assert all(term.startswith("ztech") for term in first.protected_terms)
    assert {"gatewaytimeouterror", "e504", "upstream_server", "llama", "cpp"} <= set(first.lexical_terms)


def test_versioned_lexical_index_backfills_and_rebuilds(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-zh", "snippet", "https://example.test", "SQLite", "example.test", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "text", "SQLite 的预写式日志支持并发读取", source_id="cap-zh")

    conn = database.get_db(user_id)
    try:
        row = conn.execute("SELECT analyzer_version,terms,scripts FROM atomic_lexical_documents WHERE atomic_id=?", (atomic_id,)).fetchone()
        assert row["analyzer_version"] == ANALYZER_VERSION
        assert "zhan2" in row["terms"]
        conn.execute("DELETE FROM atomic_lexical_documents WHERE atomic_id=?", (atomic_id,))
        conn.commit()
    finally:
        conn.close()

    result = database.rebuild_lexical_index(user_id)
    assert result["indexed"] == 1
    assert database.search_atomics(user_id, "预写式日志并发读取")[0]["id"] == atomic_id


def test_no_whitespace_thai_query_uses_ngram_fallback(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-th", "snippet", "https://example.test", "TLS", "example.test", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "text", "ไคลเอนต์ต้องตรวจสอบชื่อโฮสต์และใบรับรองTLSก่อนเชื่อมต่อ", source_id="cap-th")

    hits = database.search_atomics(user_id, "ตรวจสอบใบรับรองTLS")
    assert hits[0]["id"] == atomic_id
