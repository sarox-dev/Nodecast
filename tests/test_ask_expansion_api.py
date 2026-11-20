import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.services import ask_search_plan, database, memory_retrieval
from app.services.auth import hash_password


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'CONTENTS_DIR', tmp_path)
    monkeypatch.setattr(database, 'USERS_DB_PATH', tmp_path / 'users.db')
    monkeypatch.setattr(database, 'USERS_DATA_DIR', tmp_path / 'users')
    monkeypatch.setenv('NODECAST_ACCOUNT_MODE', 'shared')
    password = 'Synthetic-expansion-passphrase-37'
    uid = database.create_user_in_db('expansion-member', hash_password(password))
    other = database.create_user_in_db('private-member', 'synthetic-hash')
    ids = []
    for user, key, text in (
        (uid, 'local', 'Notes work without cloud services.'),
        (uid, 'cloud', 'Notes require a cloud server.'),
        (other, 'private', 'Notes work without cloud services.'),
    ):
        database.insert_capture_ref(user, key, 'snippet', f'https://example.invalid/{key}', key, 'example.invalid', '', '', [], '', '')
        ids.append(database.insert_atomic(user, 'text', text, source_id=key))
    calls = []
    monkeypatch.setattr(memory_retrieval, 'get_ai_assignment_for_feature', lambda *_: {'provider_id': 'synthetic', 'model': 'stub'})
    monkeypatch.setattr(memory_retrieval, 'get_ai_provider', lambda *_: {'id': 'synthetic'})
    def planner(_uid, _provider, _model, messages, **_kwargs):
        calls.append('planner')
        assert set(json.loads(messages[1]['content'])) == {'query'}
        return '{"queries":["notes"]}'
    def answer(*_args, **_kwargs):
        calls.append('answer')
        return json.dumps({'view': 'list', 'title': 'Notes', 'summary': 'Cloud is optional.', 'sections': [{'title': 'Evidence', 'content': 'Notes work without cloud.', 'evidence_ids': [ids[0]]}]})
    def stream(*_args, **_kwargs):
        calls.append('answer')
        return iter([f'VIEW: list\nTITLE: Notes\nSUMMARY: Cloud is optional.\nSECTION: Evidence\nCONTENT: Notes work without cloud.\nEVIDENCE: {ids[0]}\n'])
    monkeypatch.setattr(ask_search_plan, 'call_provider_model', planner)
    monkeypatch.setattr(memory_retrieval, 'call_provider_model', answer)
    monkeypatch.setattr(memory_retrieval, 'stream_provider_model', stream)
    client = TestClient(main.app)
    response = client.post('/auth/login', json={'username': 'expansion-member', 'password': password})
    assert response.status_code == 200, response.text
    yield client, ids[0], calls
    client.close()


def request(client, version, **options):
    body = {'query': 'piezīmes bez mākoņa', **options}
    url = '/api/memory/query'
    if version:
        body['stream_version'] = version
        url += '/stream'
    response = client.post(url, json=body)
    assert response.status_code == 200
    if not version:
        return response.json()
    event = json.loads(response.text.splitlines()[-1])
    return event['data'] if version == 1 else event['data']['result']


@pytest.mark.parametrize('version', [None, 1, 2])
def test_json_and_both_stream_versions_translate_and_enforce_original_conditions(api, version):
    client, aid, calls = api
    result = request(client, version, cross_language=True)
    assert [item['id'] for item in result['items']] == [aid]
    assert result['synthesis_status'] == 'success'
    assert calls == ['planner', 'answer']


@pytest.mark.parametrize('version', [None, 1, 2])
def test_disabling_cross_language_skips_query_planner(api, version):
    client, _aid, calls = api
    result = request(client, version, cross_language=False)
    assert result['items'] == []
    assert calls == []


@pytest.mark.parametrize('version', [None, 1, 2])
def test_no_ai_request_never_calls_configured_provider(api, version):
    client, aid, calls = api
    result = request(client, version, query='notes without cloud', synthesize=False, cross_language=True)
    assert [item['id'] for item in result['items']] == [aid]
    assert calls == []


@pytest.mark.parametrize('version', [None, 1, 2])
def test_planner_failure_preserves_supported_local_results(api, version, monkeypatch):
    client, aid, calls = api
    def fail(*_args, **_kwargs):
        raise TimeoutError('synthetic timeout')
    monkeypatch.setattr(ask_search_plan, 'call_provider_model', fail)
    result = request(client, version, query='notes without cloud', diagnostics=True)
    assert [item['id'] for item in result['items']] == [aid]
    assert result['diagnostics']['planner_status'] == 'provider_error'
    assert calls == ['answer']


@pytest.mark.parametrize('version', [None, 1, 2])
def test_missing_provider_preserves_the_no_ai_path(api, version, monkeypatch):
    client, aid, calls = api
    monkeypatch.setattr(memory_retrieval, 'get_ai_assignment_for_feature', lambda *_: None)
    result = request(client, version, query='notes without cloud')
    assert [item['id'] for item in result['items']] == [aid]
    assert result['synthesis_status'] == 'local_only'
    assert calls == []
