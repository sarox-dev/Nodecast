import copy
import json

import pytest

from app.services import database, memory_retrieval
from scripts.evaluate_ask_quality import evaluate_corpus, isolated_database, load_corpus, score_packet


def test_source_metrics_count_unique_sources_and_preserve_packet_order():
    cards = [{"id": str(i), "source_id": "a", "source_url": "a", "excerpt": "a"} for i in range(5)]
    cards.append({"id": "b", "source_id": "b", "source_url": "b", "excerpt": "b"})
    originals = {item["id"]: {"source_id": item["source_id"], "url": item["source_url"], "text": item["excerpt"]} for item in cards}
    score = score_packet(cards, ["a", "b"], originals, originals)
    assert score["actual_sources"] == ["a", "b"]
    assert score["source_precision_at_5"] == score["source_recall_at_5"] == 1
    assert score["provenance_integrity"]
    cards[-1]["source_id"] = "foreign-source"
    assert not score_packet(cards, ["a", "b"], originals, originals)["provenance_integrity"]


def test_empty_ground_truth_does_not_inflate_recall_or_precision():
    score = score_packet([], [], [], {})
    assert score["source_recall_at_5"] is None
    assert score["source_precision_at_5"] is None


def test_corpus_rejects_unknown_or_mislabeled_evidence(tmp_path):
    corpus = load_corpus()
    for change in ("duplicate", "unknown", "wrong_source"):
        value = copy.deepcopy(corpus)
        if change == "duplicate":
            value["queries"].append(value["queries"][0])
        elif change == "unknown":
            value["queries"][0]["expected"] = ["unknown"]
        else:
            value["queries"][0]["expected_sources"] = ["vram"]
        file = tmp_path / "corpus.json"
        file.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(ValueError):
            load_corpus(file)


def test_evaluation_restores_database_paths_after_failure():
    paths = (database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR)
    with pytest.raises(RuntimeError, match="interrupted evaluation"):
        with isolated_database():
            assert database.USERS_DB_PATH != paths[1]
            raise RuntimeError("interrupted evaluation")
    assert (database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR) == paths


def test_final_ask_packet_evaluation_is_isolated_and_never_calls_ai(monkeypatch):
    paths = (database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR)
    def forbid(*_args, **_kwargs):
        raise AssertionError("Evaluation must never contact an AI/embedding provider")
    for name in ("call_provider_model", "stream_provider_model", "get_embedding_provider", "provider_search_queries"):
        monkeypatch.setattr(memory_retrieval, name, forbid)
    report = evaluate_corpus(load_corpus())
    assert (database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR) == paths
    assert report["queries"] == 15
    rows = {row["id"]: row for row in report["results"]}
    for case in ("diverse_5", "diverse_8"):
        assert set(rows[case]["actual_sources"]) == set(rows[case]["expected_sources"])
        assert rows[case]["selected_evidence_count"] == rows[case]["limit"]
    assert rows["rejected"]["actual_sources"] == []
    assert rows["nfc"]["source_recall_at_5"] == 1
    assert report["metrics"]["provenance_integrity"]
    assert all(row["token_estimate"] <= row["token_budget"] for row in report["results"])
