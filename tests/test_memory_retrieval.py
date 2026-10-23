from app.services import database
from app.services import memory_retrieval
from app.services.ai_client import AIClientError
from app.services.atomic_extraction import split_evidence
from app.services.memory_retrieval import detect_intent, focused_graph, memory_constellation, query_memory, recent_memory, relation_feedback, stream_memory_query, stream_memory_query_v2


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
    assert result["synthesis"]["status"] == "local_only"
    assert result["synthesis_status"] == "local_only"


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


def test_constellation_groups_evidence_by_source_and_only_uses_accepted_semantic_edges(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com/docker", "Docker guide", "example.com", "", "2026-10-21", [], "", "")
    first = database.insert_atomic(user_id, "definition", "Docker packages applications into containers.", source_id="cap-a")
    second = database.insert_atomic(user_id, "claim", "Containers share the host kernel.", source_id="cap-a")
    concept = database.insert_atomic(user_id, "technology", "Docker", role="concept", canonical_key="docker", relevance=.9)
    database.insert_atomic_relation(user_id, first, second, "precedes", 1, method="structural", status="accepted")
    database.insert_atomic_relation(user_id, first, concept, "defines", .9, method="ai", confidence=.9, status="accepted")
    database.insert_atomic_relation(user_id, second, concept, "mentions", .6, method="ai", confidence=.6, status="candidate")

    result = memory_constellation(user_id, limit=12)

    assert {node["id"] for node in result["nodes"]} == {"source:cap-a", concept}
    assert result["edges"] == [{
        "source_id": "source:cap-a", "target_id": concept,
        "relation_type": "defines", "confidence": .9,
    }]
    assert next(node for node in result["nodes"] if node["id"] == "source:cap-a")["weight"] == 2


def test_ai_auth_error_is_returned_as_actionable_synthesis_status(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "AI source", "example.com", "", "", [], "", "")
    database.insert_atomic(user_id, "text", "AI agents use saved context", source_id="cap-a")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda _uid, feature: {"provider_id":"provider-a","model":"broken-model"} if feature == "recall_synthesis" else None)
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"base_url":"https://provider.invalid","api_key_encrypted":""})
    monkeypatch.setattr(memory_retrieval, "call_provider_model", lambda *args, **kwargs: (_ for _ in ()).throw(AIClientError("ai_authentication_failed", "AI provider authentication failed. Check the API key in Settings → AI.", 401)))
    result = query_memory(user_id, "AI", limit=5)
    assert result["items"]
    assert result["synthesis"] == {
        "status":"error", "code":"ai_authentication_failed",
        "message":"AI provider authentication failed. Check the API key in Settings → AI.",
        "http_status":401, "model":"broken-model",
    }
    assert result["synthesis_status"] == "error"
    assert result["evidence"] == result["items"]
    assert result["sources"][0]["url"] == "https://example.com"


def test_local_query_never_calls_ai_when_synthesis_is_disabled(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Local source", "example.com", "", "", [], "", "")
    database.insert_atomic(user_id, "text", "Local retrieval remains available.", source_id="cap-a")
    monkeypatch.setattr(memory_retrieval, "_ai_synthesis", lambda *_: (_ for _ in ()).throw(AssertionError("AI must not run")))
    result = query_memory(user_id, "local retrieval", synthesize=False)
    assert result["synthesis_status"] == "local_only"
    assert result["items"]


def test_recall_synthesis_uses_only_its_own_assignment_and_cites_evidence(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Docker guide", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "definition", "Docker packages applications into containers.", source_id="cap-a")
    requested_features = []
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda _uid, feature: requested_features.append(feature) or ({"provider_id":"provider-a","model":"recall-model"} if feature == "recall_synthesis" else None))
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"base_url":"https://provider.invalid","api_key_encrypted":""})
    monkeypatch.setattr(memory_retrieval, "call_provider_model", lambda *_args, **_kwargs: '{"view":"focus","title":"Docker","summary":"Saved Docker definition.","sections":[{"title":"Definition","content":"Docker packages applications into containers.","evidence_ids":["' + atomic_id + '"]}]}')
    result = query_memory(user_id, "What did I save about Docker?", limit=5)
    assert requested_features == ["recall_synthesis"]
    assert result["synthesis_status"] == "success"
    assert result["answer"]["sections"][0]["evidence_ids"] == [atomic_id]


def test_streamed_recall_emits_early_evidence_and_validated_result(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Docker guide", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "definition", "Docker packages applications into containers.", source_id="cap-a")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"provider-a", "model":"recall-model"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"provider-a"})
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", lambda *_args, **_kwargs: iter([
        "VIEW: focus\nTITLE: Docker\nSUMMARY: Docker is saved as container evidence.\nSECTION: Definition\nCONTENT: Docker packages applications into containers.\nEVIDENCE: ",
        atomic_id + "\n",
    ]))
    events = list(stream_memory_query(user_id, "What did I save about Docker?", limit=5))
    assert events[0]["event"] == "meta"
    assert events[0]["data"]["items"][0]["id"] == atomic_id
    assert any(event["event"] == "delta" and "Docker packages" in event["text"] for event in events)
    assert events[-1]["data"]["synthesis_status"] == "success"
    assert events[-1]["data"]["answer"]["sections"][0]["evidence_ids"] == [atomic_id]


def test_streamed_recall_requests_configured_response_language(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Docker guide", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "definition", "Docker packages applications into containers.", source_id="cap-a")
    captured = {}
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"provider-a", "model":"recall-model"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"provider-a"})

    def fake_stream(_user_id, _provider, _model, messages, **_kwargs):
        captured["instructions"] = messages[0]["content"]
        return iter([f"VIEW: focus\nTITLE: Docker\nSUMMARY: Kopsavilkums.\nSECTION: Definīcija\nCONTENT: Docker apraksts.\nEVIDENCE: {atomic_id}\n"])

    monkeypatch.setattr(memory_retrieval, "stream_provider_model", fake_stream)
    events = list(stream_memory_query_v2(user_id, "Ko es saglabāju par Docker?", response_language="lv"))

    assert "BCP-47 language lv" in captured["instructions"]
    assert next(item for item in events if item["event"] == "query.analyzed")["data"]["response_language"] == "lv"
    assert events[-1]["data"]["result"]["synthesis_status"] == "success"


def test_v2_stream_has_ordered_typed_events_without_chain_of_thought(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap", "snippet", "https://example.com", "Docker", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "text", "Docker container evidence", source_id="cap")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: None)
    events = list(stream_memory_query_v2(user_id, "What did I save about Docker?", request_id="req-1"))
    assert [item["seq"] for item in events] == list(range(1, len(events) + 1))
    assert events[0]["event"] == "request.started"
    assert events[-1]["event"] == "request.completed"
    assert all(item["version"] == "2.0" and item["request_id"] == "req-1" for item in events)
    analysis = next(item for item in events if item["event"] == "query.analyzed")["data"]
    assert "reasoning" not in analysis and "chain_of_thought" not in analysis
    selected = next(item for item in events if item["event"] == "evidence.selected")
    assert selected["data"]["result"]["items"][0]["id"] == atomic_id


def test_v2_stream_cancellation_stops_pipeline(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: None)
    calls = iter([False, True])
    events = list(stream_memory_query_v2(user_id, "Docker", cancel_check=lambda: next(calls)))
    assert events[-1]["event"] == "request.cancelled"
    assert not any(item["event"] == "request.completed" for item in events)


def test_v2_local_only_stream_never_opens_synthesis_provider(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap", "snippet", "https://example.com", "Docker", "example.com", "", "", [], "", "")
    database.insert_atomic(user_id, "text", "Docker container evidence", source_id="cap")
    monkeypatch.setattr(memory_retrieval, "stream_memory_query", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider stream must not open")))
    events = list(stream_memory_query_v2(user_id, "Docker", synthesize=False))
    assert [item["event"] for item in events][-2:] == ["usage", "request.completed"]
