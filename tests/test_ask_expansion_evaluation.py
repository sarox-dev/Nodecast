import pytest

from app.services import ask_search_plan, database
from scripts.evaluate_ask_expansion import CORPUS, evaluate_expansion
from scripts.evaluate_ask_quality import load_corpus


def test_translated_v2_packets_keep_constraints_sources_and_provenance():
    before = (database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR)
    report = evaluate_expansion(load_corpus(CORPUS))
    assert (database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR) == before
    assert report['queries'] == 7
    assert report['metrics']['provenance_integrity']
    for row in report['results']:
        assert set(row['expected_sources']) == set(row['actual_sources']), row['id']
        assert row['forbidden_source_hits'] == []
    assert any(row['initial_local_sources'] == [] and row['actual_sources'] for row in report['results'])


def test_real_observed_full_sentence_translation_does_not_match_articles():
    corpus = load_corpus(CORPUS)
    case = next(row for row in corpus['queries'] if row['id'] == 'context_lv')
    case['planner_queries'] = ['Why does a longer context window increase memory requirements?']
    report = evaluate_expansion(corpus)
    result = next(row for row in report['results'] if row['id'] == 'context_lv')
    assert result['actual_sources'] == ['context']
    assert result['performed_queries'] == ['longer context window increase memory requirements']


@pytest.mark.parametrize('query, alternative', [
    ('piezīmes bez mākoņa', 'notes'),
    ('piezīmes bez mākoņa izņemot Dropbox', 'notes'),
    ('notes excluding "Dropbox Sync"', 'notes synchronization'),
])
def test_supported_constraints_allow_translation_without_weakening_the_original(query, alternative):
    calls = []
    def planner(original):
        calls.append(original)
        return '{"queries":["' + alternative + '"]}'
    assert ask_search_plan.plan_search_queries(query, planner) == [query, alternative]
    assert calls == [query]


@pytest.mark.parametrize('query, bad, good', [
    ('Kas palielina KV atmiņu?', 'cloud storage', 'KV cache memory'),
    ('Kā SQLite WAL strādā?', 'PostgreSQL transactions', 'SQLite WAL concurrent readers'),
    ('Kā darbojas llama.cpp?', 'Ollama inference', 'llama.cpp inference'),
])
def test_alternatives_cannot_drop_protected_identifiers(query, bad, good):
    import json
    trace = {}
    assert ask_search_plan.plan_search_queries(query, lambda _: json.dumps({'queries': [bad, good]}), trace) == [query, good]
    assert trace['rejected_alternatives'] == 1


def test_translation_does_not_add_new_negation_or_relax_unsupported_constraints():
    query = 'piezīmes'
    assert ask_search_plan.plan_search_queries(query, lambda _: '{"queries":["notes without cloud"]}') == [query]
    def forbid(_):
        raise AssertionError('Unsupported constraints retain the guarded local path')
    for value in ('piezīmes bez mākoņa un ne Dropbox', 'notes after 2025', '"exact phrase"', 'C++'):
        assert ask_search_plan.plan_search_queries(value, forbid) == [value]
