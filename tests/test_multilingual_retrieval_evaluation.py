import json

from scripts.evaluate_multilingual_retrieval import DEFAULT_CORPUS_PATH, evaluate, load_corpus


def test_multilingual_corpus_has_required_language_and_query_families():
    corpus = load_corpus()
    scripts = {capture["script"] for capture in corpus["captures"]}
    languages = {capture["language"] for capture in corpus["captures"]}
    kinds = {query["kind"] for query in corpus["queries"]}

    assert {"Latn", "Cyrl", "Arab", "Hans", "Thai"} <= scripts
    assert {"lv", "en", "ru", "ar", "zh-Hans", "tr", "th", "und"} <= languages
    assert {"same_language", "cross_language", "technical_identifier", "comparison", "full_page", "negative"} <= kinds
    assert any(capture.get("indexed") is False and capture["capture_type"] == "page" for capture in corpus["captures"])


def test_multilingual_evaluator_is_isolated_deterministic_and_reports_known_gaps():
    report = evaluate()
    rows = {row["id"]: row for row in report["results"]}

    assert report["captures"] == 10
    assert report["queries"] == 14
    assert report["capabilities"] == {
        "lexical": True,
        "multilingual_embeddings": False,
        "external_ai_calls": False,
    }
    assert report["metrics"]["source_span_fidelity"] == 1.0
    assert rows["mixed_identifier"]["source_recall_at_5"] == 1.0
    assert rows["same_zh_wal"]["source_recall_at_5"] == 1.0
    assert rows["same_th_tls"]["source_recall_at_5"] == 1.0
    assert rows["cross_lv_en_vram"]["source_recall_at_5"] == 0.0
    assert rows["full_page_not_indexed"]["source_recall_at_5"] == 0.0
    assert rows["full_page_not_indexed"]["expected_current_gap"] == "saved_not_indexed"
    assert rows["same_lv_compare"]["intent"] == "compare"


def test_multilingual_fixture_contains_no_real_user_data():
    raw = DEFAULT_CORPUS_PATH.read_text(encoding="utf-8")
    corpus = json.loads(raw)

    assert all(capture["site"] == "example.test" for capture in corpus["captures"])
    assert all(capture["url"].startswith("https://example.test/") for capture in corpus["captures"])
