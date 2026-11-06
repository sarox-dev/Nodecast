from app.services import database, memory_retrieval, recall_cache


def test_question_normalization_preserves_sensitive_syntax():
    assert recall_cache.normalize_query(' Kas ir Docker?? ') == recall_cache.normalize_query('kas ir docker?')
    assert recall_cache.normalize_query('Kas ir Docker.') == recall_cache.normalize_query('kas ir docker?')
    assert recall_cache.normalize_query('Kas ir C++?') != recall_cache.normalize_query('Kas ir C?')
    assert recall_cache.normalize_query('Kas ir C#?') != recall_cache.normalize_query('Kas ir C?')
    assert recall_cache.normalize_query('Version 3.10?') != recall_cache.normalize_query('Version 3.1?')
    assert recall_cache.normalize_query('Find "Foo"?') != recall_cache.normalize_query('Find "foo"?')


def test_cache_keys_match_case_and_extra_question_mark_with_same_evidence():
    args = ([{"id":"one"}], 1, {"model":"m"}, {"id":"p"}, "auto", "auto")
    assert recall_cache.cache_key("What is Docker?", *args) == recall_cache.cache_key("what is docker???", *args)


def setup_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    uid = database.create_user_in_db("cache-user", "hash")
    database.insert_capture_ref(uid, "cache_test_001", "page", "https://example.com", "Docker", "example.com", "", "", [], "", "")
    aid = database.insert_atomic(uid, "text", "Docker container runtime", source_id="cache_test_001")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"m"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"p"})
    calls = []
    def provider(*_args, **_kwargs):
        calls.append(1)
        yield f"VIEW: focus\nTITLE: Docker\nSUMMARY: Saved Docker evidence.\nSECTION: Docker\nCONTENT: Container runtime.\nEVIDENCE: {aid}\n"
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", provider)
    return uid, calls


def answer(uid, *, force=False):
    return list(memory_retrieval.stream_memory_query(uid, "Docker", force_refresh=force))[-1]["data"]


def test_cache_hit_force_and_capture_change_invalidation(tmp_path, monkeypatch):
    uid, calls = setup_cache(tmp_path, monkeypatch)
    assert answer(uid)["cache"]["hit"] is False
    assert answer(uid)["cache"]["hit"] is True
    assert len(calls) == 1
    assert answer(uid, force=True)["cache"]["hit"] is False
    assert len(calls) == 2
    database.insert_capture_ref(uid, "cache_test_002", "page", "https://example.com/2", "New", "example.com", "", "", [], "", "")
    assert answer(uid)["cache"]["hit"] is False
    assert len(calls) == 3


def test_case_and_question_marks_hit_cache_through_stream(tmp_path, monkeypatch):
    uid, calls = setup_cache(tmp_path, monkeypatch)
    first = list(memory_retrieval.stream_memory_query(uid, "Docker?"))[-1]["data"]
    second = list(memory_retrieval.stream_memory_query(uid, "docker???"))[-1]["data"]
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert len(calls) == 1


def test_invalidation_during_synthesis_does_not_store_stale_answer(tmp_path, monkeypatch):
    uid, calls = setup_cache(tmp_path, monkeypatch)
    original = memory_retrieval.stream_provider_model
    def changing(*args, **kwargs):
        for delta in original(*args, **kwargs):
            database.insert_capture_ref(uid, "cache_test_002", "page", "", "New", "", "", "", [], "", "")
            yield delta
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", changing)
    answer(uid)
    conn = database.get_db(uid)
    try: assert conn.execute("SELECT COUNT(*) FROM recall_answer_cache").fetchone()[0] == 0
    finally: conn.close()


def test_cache_can_be_disabled_and_cleared(tmp_path, monkeypatch):
    uid, calls = setup_cache(tmp_path, monkeypatch)
    answer(uid)
    assert recall_cache.clear(uid) == 1
    assert answer(uid)["cache"]["hit"] is False
    database.set_user_setting(uid, "recall_cache_enabled", "false")
    assert answer(uid)["cache"]["hit"] is False
    assert len(calls) == 3


def test_cache_does_not_cross_accounts_or_cache_invalid_output(tmp_path, monkeypatch):
    uid, calls = setup_cache(tmp_path, monkeypatch)
    answer(uid)
    other = database.create_user_in_db("cache-other", "hash")
    database.insert_capture_ref(other, "cache_test_001", "page", "https://example.com", "Docker", "example.com", "", "", [], "", "")
    database.insert_atomic(other, "text", "Docker container runtime", source_id="cache_test_001")
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", lambda *_args, **_kwargs: iter(["invalid output"]))
    assert answer(other)["synthesis_status"] == "error"
    assert answer(other)["synthesis_status"] == "error"
    conn = database.get_db(other)
    try: assert conn.execute("SELECT COUNT(*) FROM recall_answer_cache").fetchone()[0] == 0
    finally: conn.close()


def test_cache_does_not_reuse_different_provider_or_language(tmp_path, monkeypatch):
    uid, calls = setup_cache(tmp_path, monkeypatch)
    answer(uid)
    result = list(memory_retrieval.stream_memory_query(uid, "Docker", response_language="lv"))[-1]["data"]
    assert result["cache"]["hit"] is False
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"other"})
    assert answer(uid)["cache"]["hit"] is False
    assert len(calls) == 3
