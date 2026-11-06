"""Synthetic, isolated baseline: report gaps rather than asserting retrieval quality."""
import json
from pathlib import Path

from app.services import database, memory_retrieval


CORPUS = Path(__file__).parent / "fixtures" / "ask_retrieval_eval.json"


def test_synthetic_eval_measures_candidate_and_packet_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CONTENTS_DIR", tmp_path)
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    corpus = json.loads(CORPUS.read_text())
    uid = database.create_user_in_db("ask-eval", "not-a-login-hash")
    keys = {}
    for capture in corpus["captures"]:
        database.insert_capture_ref(uid, capture["id"], "snippet", "https://example.test/" + capture["id"], capture["title"], "example.test", "", "", [], "", "")
        for key, text in capture["evidence"]:
            keys[key] = database.insert_atomic(uid, "text", text, source_id=capture["id"], context_header=capture["title"])
    report = {}
    for case in corpus["queries"]:
        candidates, _ = memory_retrieval._candidate_search(uid, case["query"], limit=30)
        _result, packet, _intent = memory_retrieval._memory_context(uid, case["query"], 8, 700, "auto")
        expected = {keys[key] for key in case["expected"]}
        candidate_ids = {item["id"] for item in candidates}
        packet_ids = {item["id"] for item in packet}
        report[case["id"]] = {
            "candidate_found": len(expected & candidate_ids), "packet_found": len(expected & packet_ids),
            "expected_count": len(expected), "irrelevant_selected": len(packet_ids & {keys[k] for k in case["irrelevant"]}),
            "answer_policy": case.get("answer_policy"),
        }
    assert len(report) == 8
    assert report["error"]["packet_found"] == 1
    assert report["notes_sync"]["packet_found"] == 2
    assert report["notes_sync"]["irrelevant_selected"] == 1  # still available when space permits
    assert all(row["packet_found"] <= row["candidate_found"] <= row["expected_count"] for row in report.values())
    assert report["personal_reason"]["answer_policy"] == "personal_intent_unconfirmed"
    assert report["missing"]["answer_policy"] == "do_not_invent"
    case = next(case for case in corpus["queries"] if case["id"] == "context_lv")
    _, expanded, _ = memory_retrieval._memory_context(uid, case["query"], 8, 700, "auto", alternative_queries=["context length KV cache memory"])
    assert keys["context"] in {item["id"] for item in expanded}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
