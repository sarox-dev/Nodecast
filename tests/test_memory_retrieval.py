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


def test_evidence_selection_preserves_exact_short_results_and_diversity():
    select = memory_retrieval._select_evidence_candidates
    items = [
        {"id":"nav", "source_id":"a", "content":"r/foss"},
        {"id":"one", "source_id":"a", "content":"Joplin supports WebDAV."},
        {"id":"two", "source_id":"a", "content":"Logseq supports file sync."},
        {"id":"short", "source_id":"b", "content":"Metal — Apple Silicon"},
        {"id":"three", "source_id":"a", "content":"Third useful item."},
    ]
    assert [i['id'] for i in select(items, 'Obsidian sync', 5)] == ['one','two','short','three','nav']
    assert select(items, 'r/foss', 1)[0]['id'] == 'nav'
    assert select([items[3]], 'Metal', 1)[0]['id'] == 'short'


def test_evidence_keeps_short_selection_and_multiline_context_together():
    text = "Brave means courage. It describes someone facing danger.\nExample: a brave soldier."
    assert [item["content"] for item in split_evidence(text)] == [text]
    table = "Backend\tDevice\nCUDA\tNvidia GPU\nMetal\tApple Silicon"
    assert [item["content"] for item in split_evidence(table)] == [table]


def test_long_evidence_is_bounded_ordered_and_not_truncated():
    text = "\n\n".join(f"Paragraph {i}: " + "meaningful text " * 75 for i in range(60))
    blocks = split_evidence(text)
    assert len(blocks) > 50
    assert max(len(item["content"]) for item in blocks) <= 600
    assert [item["position"] for item in blocks] == list(range(len(blocks)))
    assert " ".join(text.split()) == " ".join(" ".join(item["content"] for item in blocks).split())


def test_long_unbroken_text_is_not_lost():
    text = "x" * 1500
    blocks = split_evidence(text)
    assert [len(item["content"]) for item in blocks] == [600, 600, 300]
    assert "".join(item["content"] for item in blocks) == text


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
    assert result["synthesis"]["code"] == "provider_unavailable"


def test_empty_search_reports_distinct_reasons_without_calling_ai(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    monkeypatch.setattr(memory_retrieval, "_ai_synthesis", lambda *_: (_ for _ in ()).throw(AssertionError("AI must not run without evidence")))
    def check(code):
        assert query_memory(user_id, "unrelated query")["synthesis"]["code"] == code
        assert list(stream_memory_query(user_id, "unrelated query"))[-1]["data"]["synthesis"]["code"] == code
        assert list(stream_memory_query_v2(user_id, "unrelated query"))[-1]["data"]["result"]["synthesis"]["code"] == code
    check("no_saved_sources")
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Example", "example.com", "", "", [], "", "")
    check("no_indexed_evidence")
    database.insert_atomic(user_id, "text", "Docker containers", source_id="cap-a")
    check("no_matching_evidence")


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
    assert result["page"] == {"cursor": None, "has_more": False}


def test_bounded_query_does_not_advertise_unavailable_next_page(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    for index in range(12):
        capture_id = f"page-{index}"
        database.insert_capture_ref(user_id, capture_id, "snippet", f"https://example.com/{index}", "Design", "example.com", "", "", [], "", "")
        database.insert_atomic(user_id, "text", f"Nodecast design evidence {index}", source_id=capture_id)
    result = query_memory(user_id, "Nodecast design", limit=8, synthesize=False)
    assert len(result["items"]) == 8
    assert result["page"] == {"cursor": None, "has_more": False}


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


def test_stream_hides_inline_evidence_id_even_when_split_between_deltas(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-id", "snippet", "https://example.com", "Google", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "text", "Founders information", source_id="cap-id")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"m"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"p"})
    raw = f"VIEW: focus\nTITLE: Google\nSUMMARY: Founders [{atomic_id}] [ordinary text].\nSECTION: People\nCONTENT: Two founders [{atomic_id}].\nEVIDENCE: {atomic_id}\n"
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", lambda *_args, **_kwargs: iter(raw))
    events = list(stream_memory_query(user_id, "founders"))
    displayed = ''.join(event.get("text", "") for event in events if event["event"] == "delta")
    answer = events[-1]["data"]["answer"]
    assert atomic_id not in displayed
    assert "[ordinary text]" in displayed
    assert atomic_id not in answer["summary"]
    assert atomic_id not in answer["sections"][0]["content"]
    assert answer["sections"][0]["evidence_ids"] == [atomic_id]


def test_inline_citations_preserve_positions_and_reject_unknown_ids(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-inline", "snippet", "https://example.com", "Search", "example.com", "", "", [], "", "")
    aid = database.insert_atomic(user_id, "text", "Search engine example", source_id="cap-inline")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"m"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"p"})
    raw = f"VIEW: focus\nTITLE: Search\nSUMMARY: First claim. [EVIDENCE: {aid}] Next. [EVIDENCE: unknown]\nSECTION: Example\nCONTENT: Example claim. [EVIDENCE: {aid}]\nEVIDENCE: {aid}\n"
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", lambda *_args, **_kwargs: iter(raw))
    events = list(stream_memory_query(user_id, "search"))
    displayed = ''.join(event.get("text", "") for event in events if event["event"] == "delta")
    assert aid not in displayed and "EVIDENCE:" not in displayed
    answer = events[-1]["data"]["answer"]
    assert answer["summary_parts"] == [{"text":"First claim. "}, {"evidence_id":aid}, {"text":" Next. "}]
    assert answer["sections"][0]["content_parts"] == [{"text":"Example claim. "}, {"evidence_id":aid}]


def test_streamed_recall_requests_configured_response_language(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Docker guide", "example.com", "", "", [], "", "")
    atomic_id = database.insert_atomic(user_id, "definition", "Docker packages applications into containers.", source_id="cap-a")
    captured = {}
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"provider-a", "model":"recall-model"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"provider-a"})
    monkeypatch.setattr(memory_retrieval, "provider_search_queries", lambda _u, _p, _m, q: [q])

    def fake_stream(_user_id, _provider, _model, messages, **_kwargs):
        captured["instructions"] = messages[0]["content"]
        return iter([f"VIEW: focus\nTITLE: Docker\nSUMMARY: Kopsavilkums.\nSECTION: Definīcija\nCONTENT: Docker apraksts.\nEVIDENCE: {atomic_id}\n"])

    monkeypatch.setattr(memory_retrieval, "stream_provider_model", fake_stream)
    events = list(stream_memory_query_v2(user_id, "Ko es saglabāju par Docker?", response_language="lv"))

    assert "BCP-47 language lv" in captured["instructions"]
    assert next(item for item in events if item["event"] == "query.analyzed")["data"]["response_language"] == "lv"
    assert events[-1]["data"]["result"]["synthesis_status"] == "success"


def test_expanded_search_recovers_evidence_after_empty_local_query_and_is_user_scoped(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Saved notes", "example.com", "", "", [], "", "")
    aid = database.insert_atomic(user_id, "text", "LAG MMLU Latvian benchmark", source_id="cap-a")
    other = database.create_user_in_db("other-user", "hash")
    database.insert_capture_ref(other, "cap-b", "snippet", "https://example.com/private", "Private", "example.com", "", "", [], "", "")
    database.insert_atomic(other, "text", "LAG MMLU Latvian benchmark", source_id="cap-b")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"m"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"p"})
    monkeypatch.setattr(memory_retrieval, "provider_search_queries", lambda _u, _p, _m, q: [q, "LAG MMLU Latvian benchmark"])
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", lambda *_args, **_kwargs: iter([f"VIEW: focus\nTITLE: Benchmark\nSUMMARY: Saved benchmark.\nSECTION: Evidence\nCONTENT: Latvian benchmark.\nEVIDENCE: {aid}\n"]))
    events = list(stream_memory_query_v2(user_id, "meklējamais vārds"))
    searches = [event["data"]["query"] for event in events if event["event"] == "search.performed"]
    assert searches == ["LAG MMLU Latvian benchmark"]
    selected = [event["data"]["result"] for event in events if event["event"] == "evidence.selected"]
    assert selected[0]["items"] == []
    result = events[-1]["data"]["result"]
    assert [item["id"] for item in result["items"]] == [aid]
    assert result["answer"]["sections"][0]["evidence_ids"] == [aid]


def test_expansion_failure_preserves_original_results(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Docker", "example.com", "", "", [], "", "")
    aid = database.insert_atomic(user_id, "text", "Docker container evidence", source_id="cap-a")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"m"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"p"})
    monkeypatch.setattr(memory_retrieval, "provider_search_queries", lambda *_: (_ for _ in ()).throw(RuntimeError("planner failed")))
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", lambda *_args, **_kwargs: iter([f"VIEW: focus\nTITLE: Docker\nSUMMARY: Saved.\nSECTION: Evidence\nCONTENT: Docker.\nEVIDENCE: {aid}\n"]))
    result = list(stream_memory_query_v2(user_id, "Docker"))[-1]["data"]["result"]
    assert result["items"][0]["id"] == aid
    assert result["synthesis_status"] == "success"


def test_expanded_stream_cache_uses_selected_evidence(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap-a", "snippet", "https://example.com", "Notes", "example.com", "", "", [], "", "")
    aid = database.insert_atomic(user_id, "text", "Joplin synchronization", source_id="cap-a")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"m"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"p"})
    monkeypatch.setattr(memory_retrieval, "provider_search_queries", lambda _u, _p, _m, q: [q, "Joplin synchronization"])
    calls = []
    def model(*_args, **_kwargs):
        calls.append(1)
        return iter([f"VIEW: focus\nTITLE: Notes\nSUMMARY: Saved.\nSECTION: Evidence\nCONTENT: Sync.\nEVIDENCE: {aid}\n"])
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", model)
    first = list(stream_memory_query_v2(user_id, "piezīmes"))[-1]["data"]["result"]
    second = list(stream_memory_query_v2(user_id, "piezīmes"))[-1]["data"]["result"]
    assert first["cache"]["hit"] is False and second["cache"]["hit"] is True
    assert second["items"][0]["id"] == aid and len(calls) == 1


def test_diagnostics_are_opt_in_and_contain_only_status_and_counts(tmp_path, monkeypatch):
    user_id = _user_db(tmp_path, monkeypatch)
    database.insert_capture_ref(user_id, "cap", "snippet", "https://example.com", "Sensitive title", "example.com", "", "", [], "", "")
    aid = database.insert_atomic(user_id, "text", "Docker private evidence", source_id="cap")
    monkeypatch.setattr(memory_retrieval, "get_ai_assignment_for_feature", lambda *_: {"provider_id":"p", "model":"m"})
    monkeypatch.setattr(memory_retrieval, "get_ai_provider", lambda *_: {"id":"p"})
    def planner(_u, _p, _m, q, diagnostics=None):
        if diagnostics is not None: diagnostics['planner_status'] = 'success'
        return [q, 'Docker']
    monkeypatch.setattr(memory_retrieval, "provider_search_queries", planner)
    monkeypatch.setattr(memory_retrieval, "stream_provider_model", lambda *_args, **_kwargs: iter([f"VIEW: focus\nTITLE: Docker\nSUMMARY: Saved.\nSECTION: Evidence\nCONTENT: Docker.\nEVIDENCE: {aid}\n"]))
    normal = list(stream_memory_query_v2(user_id, "secret query"))[-1]['data']['result']
    assert 'diagnostics' not in normal
    result = list(stream_memory_query_v2(user_id, "secret query", diagnostics=True))[-1]['data']['result']
    trace = result['diagnostics']
    assert trace == {'planner_status':'success', 'alternative_queries':1, 'original_candidates':0, 'alternative_candidate_counts':[1], 'merged_candidates':1, 'selected_evidence':1}
    assert 'secret' not in str(trace) and 'private' not in str(trace) and aid not in str(trace)


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
