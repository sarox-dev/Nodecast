from app.services import database
from app.services import memory_retrieval
from app.services.ai_client import AIClientError
from app.services.atomic_extraction import split_evidence
from app.services.memory_retrieval import detect_intent, focused_graph, query_memory, recent_memory, relation_feedback


def _user_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CONTENTS_DIR", tmp_path)
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    user_id = database.create_user_in_db("memory-tester", "hash", True)
    database.init_user_db(user_id)
    return user_id


def test_deterministic_evidence_preserves_order_and_problem_identity():
    text = "Docker is a container runtime.\n\nPermissionError: socket denied.\n\n1. Add the user to the docker group."
    evidence = split_evidence(text, "Troubleshooting")
    assert [item["position"] for item in evidence] == [0, 1, 2]
    assert [item["type"] for item in evidence] == ["definition", "problem", "procedure_step"]
    assert "PermissionError" in evidence[1]["content"]


def test_exact_error_query_returns_traceable_local_fallback(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://docs.example/error", "Socket guide", "docs.example", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "problem", "PermissionError: Docker socket denied", source_id="cap-a", role="evidence")
    result = query_memory(user_id, "PermissionError Docker socket", limit=5)
    assert result["query"]["intent"] == "problem"
    assert result["items"][0]["id"] == atomic_id
    assert result["items"][0]["source_url"] == "https://docs.example/error"
    assert result["synthesis"]["status"] == "unavailable"


def test_domain_does_not_create_relation_and_rejection_is_persisted(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    for cid, path, text in (("a", "news", "Election result"), ("b", "recipe", "Pancake recipe")):
        database.insert_capture_ref(user_id, cid, "snippet", f"https://tvnet.lv/{path}", text, "tvnet.lv", "", "", [], "", "")
    first = database.insert_atomic(user_id, "claim", "Election result", source_id="a")
    second = database.insert_atomic(user_id, "procedure_step", "Pancake recipe", source_id="b")
    conn = database.get_db(user_id)
    try:
        assert conn.execute("SELECT COUNT(*) FROM atomic_relations").fetchone()[0] == 0
    finally:
        conn.close()
    relation_id = database.insert_atomic_relation(user_id, first, second, "semantically_related", method="embedding", confidence=.51)
    assert relation_feedback(user_id, relation_id, "not_related")
    conn = database.get_db(user_id)
    try:
        assert conn.execute("SELECT status FROM atomic_relations WHERE id=?", (relation_id,)).fetchone()[0] == "rejected"
    finally:
        conn.close()


def test_comparison_intent():
    assert detect_intent("Docker vs Kubernetes") == "compare"


def test_recent_memory_parses_sqlite_json_properties(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Example", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "claim", "Original evidence", properties={"summary":"Short AI summary"}, source_id="cap-a")
    result = recent_memory(user_id)
    assert result["items"][0]["id"] == atomic_id
    assert result["items"][0]["summary"] == "Short AI summary"


def test_recent_memory_is_not_filled_by_one_long_capture(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    for source_index in range(4):
        capture_id = f"cap-{source_index}"
        database.insert_capture_ref(user_id, capture_id, "snippet", f"https://example.com/{source_index}", f"Source {source_index}", "example.com", "", f"2026-09-2{source_index}", [], "", "")
        for position in range(12):
            database.insert_atomic(user_id, "text", f"Evidence {source_index}-{position}", source_id=capture_id, position=position)
    result = recent_memory(user_id, limit=8)
    assert len(result["items"]) == 8
    assert len({item["source_id"] for item in result["items"]}) == 4


def test_focused_graph_hides_precedes_and_candidates_by_default(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Example", "example.com", "", "", [], "", "")
    first = database.insert_atomic(user_id, "text", "First", source_id="cap-a")
    second = database.insert_atomic(user_id, "text", "Second", source_id="cap-a")
    third = database.insert_atomic(user_id, "text", "Third", source_id="cap-a")
    database.insert_atomic_relation(user_id, first, second, "precedes", 1, method="structural", status="accepted")
    database.insert_atomic_relation(user_id, first, third, "supports", .7, method="ai", status="candidate")
    assert focused_graph(user_id, first)["edges"] == []
    expanded = focused_graph(user_id, first, include_candidates=True)
    assert [edge["relation_type"] for edge in expanded["edges"]] == ["supports"]


def test_ai_auth_error_is_returned_as_actionable_synthesis_status(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "AI source", "example.com", "", "", [], "", "")
    database.insert_atomic(user_id, "text", "AI agents use saved context", source_id="cap-a")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"provider-a","model":"broken-model"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"base_url":"https://provider.invalid","api_key_encrypted":""})
    monkeypatch.setattr(memory_retrieval, "decrypt_api_key", lambda *_: "bad-key")
    monkeypatch.setattr(memory_retrieval, "call_ai_model", lambda *args, **kwargs: (_ for _ in ()).throw(AIClientError("ai_authentication_failed", "AI provider authentication failed. Check the API key in Settings → AI.", 401)))
    result = query_memory(user_id, "AI", limit=5)
    assert result["items"]
    assert result["synthesis"] == {
        "status":"error", "code":"ai_authentication_failed",
        "message":"AI provider authentication failed. Check the API key in Settings → AI.",
        "http_status":401, "model":"broken-model",
    }
