"""Constraint acceptance uses original evidence, not generated descriptions."""
import pytest

from app.services import database, memory_retrieval


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'CONTENTS_DIR', tmp_path)
    monkeypatch.setattr(database, 'USERS_DB_PATH', tmp_path / 'users.db')
    monkeypatch.setattr(database, 'USERS_DATA_DIR', tmp_path / 'users')
    uid = database.create_user_in_db('constraint-member', 'synthetic-hash')

    def add(key, text):
        database.insert_capture_ref(uid, key, 'snippet', f'https://example.invalid/{key}', 'Notes / Piezīmes', 'example.invalid', '', '', [], '', '')
        return database.insert_atomic(uid, 'text', text, source_id=key, context_header='Notes / Piezīmes')

    return uid, add


@pytest.mark.parametrize('query', ['notes without cloud', 'notes with no cloud dependency', 'piezīmes bez mākoņa'])
def test_cloud_constraint_requires_affirmative_support(library, query):
    uid, add = library
    accepted = {
        add('absent', 'Notes work without a cloud server.'),
        add('optional', 'Notes: cloud synchronization is optional.'),
        add('offline', 'Notes work entirely offline.'),
        add('dependency', 'Notes have no cloud dependency.'),
        add('lv', 'Piezīmes darbojas bez mākoņa.'),
        add('lv-optional', 'Piezīmes: mākoņa sinhronizācija nav obligāta.'),
    }
    for key, text in {
        'required': 'Notes require a cloud server.',
        'mention': 'Notes support cloud synchronization.',
        'unknown': 'Notes have a useful writing interface.',
        'question': 'Can notes work without cloud services?',
        'uncertain': 'It is unclear whether notes work without cloud services.',
        'contradiction': 'Notes work offline but require a cloud account.',
        'lv-required': 'Piezīmēm nepieciešams mākoņa serveris.',
    }.items():
        add(key, text)
    result = memory_retrieval.query_memory(uid, query, synthesize=False)
    assert {item['id'] for item in result['items']} == accepted
    assert result['query']['text'] == query
    assert result['retrieval']['constraints']['unknown'] > 0


def test_constraint_does_not_invent_an_absence_from_unknown_evidence(library):
    uid, add = library
    add('unknown', 'Notes support Markdown.')
    result = memory_retrieval.query_memory(uid, 'notes without cloud', synthesize=False)
    assert result['items'] == []
    assert result['retrieval']['constraints']['unknown'] == 1


def test_unconstrained_question_keeps_original_matches(library):
    uid, add = library
    expected = add('cloud', 'Notes require a cloud server.')
    result = memory_retrieval.query_memory(uid, 'notes cloud', synthesize=False)
    assert result['items'][0]['id'] == expected


@pytest.mark.parametrize('text', [
    'Notes do not work without cloud services.',
    'Without cloud, notes cannot synchronize.',
    'Notes cannot operate offline.',
    'Notes will not work entirely offline.',
    'Notes cloud synchronization is not optional.',
    'Notes work without cloud if an administrator activates the account.',
    'No cloud requirement is documented for these notes.',
    'Notes work without cloud, but need a cloud account to open the app.',
    'Piezīmes nevar darboties bez mākoņa.',
    'Piezīmes darbojas bez mākoņa, ja ir aktivizēts konts.',
    'Piezīmes: mākoņa sinhronizācija ir obligāta.',
])
def test_negated_conditional_or_conflicting_claims_are_not_positive_matches(library, text):
    uid, add = library
    add('ambiguous', text)
    assert memory_retrieval.query_memory(uid, 'notes without cloud', synthesize=False)['items'] == []


def test_quoted_words_are_search_text_not_operators(library):
    uid, add = library
    add('quote', 'An article discusses the expression without cloud.')
    result = memory_retrieval.query_memory(uid, 'notes "without cloud"', synthesize=False)
    assert result['query_analysis']['content_constraints'] == []


def test_repeated_exclusions_are_not_silently_discarded(library):
    uid, add = library
    add('last-exclusion', 'Notes use Provider8.')
    query = 'notes ' + ' '.join(f'exclude Provider{i}' for i in range(9))
    result = memory_retrieval.query_memory(uid, query, synthesize=False)
    assert result['items'] == []
    assert result['retrieval']['constraints']['applied'] == 9


@pytest.mark.parametrize('query', ['notes exclude Dropbox', 'notes excluding "Dropbox Sync"', 'piezīmes izņemot Dropbox'])
def test_literal_exclusions_preserve_positive_topic(library, query):
    uid, add = library
    good = add('local', 'Notes / piezīmes use Syncthing for synchronization.')
    add('excluded', 'Notes / piezīmes use Dropbox Sync for synchronization.')
    result = memory_retrieval.query_memory(uid, query, synthesize=False)
    assert [item['id'] for item in result['items']] == [good]


def test_constraints_apply_again_after_alternative_search(library):
    uid, add = library
    good = add('local', 'Zeta notes work without cloud services.')
    add('cloud', 'Zeta notes require cloud services.')
    result, packet, _ = memory_retrieval._memory_context(uid, 'notes without cloud', 8, 700, 'auto', alternative_queries=['Zeta cloud'])
    assert [item['id'] for item in result['items']] == [good]
    assert [item['id'] for item in packet] == [good]


def test_v2_without_ai_enforces_the_same_constraint(library, monkeypatch):
    uid, add = library
    good = add('local', 'Notes cloud synchronization is optional.')
    add('cloud', 'Notes require a cloud server.')
    def forbid(*_args, **_kwargs):
        raise AssertionError('Local-only query must not call AI')
    monkeypatch.setattr(memory_retrieval, 'provider_search_queries', forbid)
    monkeypatch.setattr(memory_retrieval, 'stream_provider_model', forbid)
    events = list(memory_retrieval.stream_memory_query_v2(uid, 'notes without cloud', synthesize=False))
    assert [item['id'] for item in events[-1]['data']['result']['items']] == [good]
