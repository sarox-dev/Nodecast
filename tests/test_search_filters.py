"""Contracts for shared manual/NL filters, scoping and complete source browsing."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.services import database, memory_retrieval, saved_search, ai_client
from app.services.auth import hash_password
from app.services.search_filters import SearchFilters, prepare_filter_context, resolve_filters, source_domain

NOW = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)


def test_saved_dates_use_calendar_boundaries_and_daylight_saving():
    result = resolve_filters({"period":"yesterday"}, "Europe/Riga", NOW)
    assert result["saved_after"] == "2026-11-18T22:00:00Z"
    assert result["saved_before"] == "2026-11-19T22:00:00Z"
    spring = resolve_filters({"period":"custom", "start_date":"2026-03-29", "end_date":"2026-03-29"}, "Europe/Riga", NOW)
    assert spring["saved_after"] == "2026-03-28T22:00:00Z"
    assert spring["saved_before"] == "2026-03-29T21:00:00Z"  # 23-hour calendar day
    fall = resolve_filters({"period":"custom", "start_date":"2026-10-25", "end_date":"2026-10-25"}, "Europe/Riga", NOW)
    assert fall["saved_after"] == "2026-10-24T21:00:00Z"
    assert fall["saved_before"] == "2026-10-25T22:00:00Z"


@pytest.mark.parametrize("query", ["Parādi visu info par Docker ko saglabāju vakar", "Show all info about Docker saved yesterday"])
def test_natural_language_shares_filter_state_without_treating_topic_as_source(query):
    context = prepare_filter_context(query, {"sources":["github.com"]}, "Europe/Riga", sources=["docker.com", "github.com"], now=NOW)
    assert context["search_text"] == "Docker"
    assert context["filters"]["period"] == "yesterday"
    assert context["filters"]["sources"] == ["github.com"]


def test_explicit_sources_and_manual_override_persist():
    context = prepare_filter_context("Docker from GitHub and YouTube yesterday", sources=["github.com","youtube.com"], now=NOW)
    assert context["filters"]["sources"] == ["github.com","youtube.com"]
    assert context["search_text"] == "Docker"
    following = prepare_filter_context("SQLite", context["filters"], now=NOW)
    assert following["filters"] == context["filters"]
    manual = prepare_filter_context("Docker yesterday", {"period":"last30"}, interpret=False, now=NOW)
    assert manual["search_text"] == "Docker"
    assert manual["filters"]["period"] == "last30"
    cleared = prepare_filter_context("Docker yesterday", {}, interpret=False, now=NOW)
    assert cleared["filters"]["period"] == "any"


@pytest.mark.parametrize("query", ['Docker "yesterday"', 'Docker `vakar`', 'Docker not yesterday', 'Docker izņemot vakar'])
def test_quoted_and_negated_metadata_is_not_silently_applied(query):
    context = prepare_filter_context(query, now=NOW)
    assert context["filters"]["period"] == "any"
    assert context["search_text"] == query


@pytest.mark.parametrize("filters", [
    {"sources":["github.com/evil"]}, {"sources":["x'); DROP TABLE captures;--"]},
    {"capture_types":["page OR 1=1"]}, {"period":"custom"},
    {"period":"custom", "start_date":"2026-12-01", "end_date":"2026-01-01"},
    {"user_id":"another-user"},
])
def test_filter_schema_rejects_unrecognized_or_unsafe_values(filters):
    with pytest.raises(ValidationError): SearchFilters.model_validate(filters)


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(database,"CONTENTS_DIR",tmp_path)
    monkeypatch.setattr(database,"USERS_DB_PATH",tmp_path/'users.db')
    monkeypatch.setattr(database,"USERS_DATA_DIR",tmp_path/'users')
    monkeypatch.setenv('NODECAST_ACCOUNT_MODE','shared')
    password = 'Synthetic-filter-passphrase-43'
    uid = database.create_user_in_db('filter-member',hash_password(password))
    other = database.create_user_in_db('other-filter-member','synthetic-hash')
    def add(key, domain='github.com', saved='2026-11-19T10:00:00Z', kind='snippet', text='Docker container runtime configuration.', user=uid, title=None):
        database.insert_capture_ref(user,key,kind,'https://'+domain+'/'+key,title or key,domain,'2020-01-01T00:00:00Z',saved,[],'','')
        return database.insert_atomic(user,'text',text,source_id=key) if text else None
    client=TestClient(main.app)
    assert client.post('/auth/login',json={'username':'filter-member','password':password}).status_code==200
    yield client,uid,other,add
    client.close()


@pytest.mark.parametrize('version',[None,1,2])
def test_every_api_path_filters_before_top_k_and_preserves_provenance(library,version):
    client,uid,other,add=library
    for index in range(40): add(f'wrong-{index}',domain='youtube.com')
    wanted=add('wanted')
    add('foreign',user=other)
    body={'query':'Docker','synthesize':False,'filters':{'sources':['github.com'],'period':'custom','start_date':'2026-11-19','end_date':'2026-11-19'},'timezone':'Europe/Riga'}
    url='/api/memory/query'
    if version: body['stream_version']=version; url+='/stream'
    response=client.post(url,json=body)
    assert response.status_code==200,response.text
    result=response.json() if not version else json.loads(response.text.splitlines()[-1])['data']
    if version==2: result=result['result']
    assert [item['id'] for item in result['items']]==[wanted]
    assert result['items'][0]['source_id']=='wanted'
    assert result['filters']['sources']==['github.com']


def test_semantic_candidates_are_scoped_before_vector_top_k(library):
    client,uid,other,add=library
    for index in range(35):
        aid=add(f'wrong-vector-{index}',domain='youtube.com')
        database.upsert_atomic_embedding(uid,aid,'test','model','r1',[1.0,0.0])
    wanted=add('wanted-vector')
    database.upsert_atomic_embedding(uid,wanted,'test','model','r1',[0.8,0.2])
    results=database.search_atomic_embeddings(uid,[1.0,0.0],'test','model','r1',limit=1,filters=resolve_filters({'sources':['github.com']}))
    assert [row['id'] for row in results]==[wanted]


def test_browse_is_paginated_source_deduplicated_and_includes_bookmarks(library):
    client,uid,other,add=library
    for index in range(25):
        add(f'save-{index:02}')
        database.insert_atomic(uid,'text','Docker second fragment.',source_id=f'save-{index:02}')
    add('bookmark',kind='bookmark',text=None,title='Docker documentation')
    add('foreign',user=other)
    first=client.post('/api/memory/browse',json={'query':'Docker','filters':{'sources':['github.com']},'limit':20}).json()
    second=client.post('/api/memory/browse',json={'query':'Docker','filters':{'sources':['github.com']},'limit':20,'offset':20}).json()
    assert first['page']['total']==26
    assert len(first['items'])==20 and first['page']['has_more']
    assert len(second['items'])==6 and not second['page']['has_more']
    ids=[row['id'] for row in first['items']+second['items']]
    assert len(set(ids))==26 and 'bookmark' in ids and 'foreign' not in ids
    facets=client.get('/api/memory/filters').json()
    assert facets['sources']==[{'value':'github.com','count':26}]


def test_time_uses_saved_not_captured_and_upper_bound_is_exclusive(library):
    client,uid,other,add=library
    add('before',saved='2026-11-18T21:59:59Z')
    add('start',saved='2026-11-18T22:00:00Z')
    add('end',saved='2026-11-19T21:59:59.999Z')
    add('next',saved='2026-11-19T22:00:00Z')
    result=client.post('/api/memory/browse',json={'query':'','filters':{'period':'custom','start_date':'2026-11-19','end_date':'2026-11-19'},'timezone':'Europe/Riga'}).json()
    assert {row['id'] for row in result['items']}=={'start','end'}


def test_manual_and_natural_date_filters_return_the_same_sources(library,monkeypatch):
    client,uid,other,add=library
    add('today',saved='2026-11-20T10:00:00Z')
    # Use an explicit range so the test does not depend on the machine clock.
    natural=client.post('/api/memory/browse',json={'query':'Docker no 2026-11-19 līdz 2026-11-20','filters':{}}).json()
    manual=client.post('/api/memory/browse',json={'query':'Docker','filters':{'period':'custom','start_date':'2026-11-19','end_date':'2026-11-20'}}).json()
    assert natural['items']==manual['items']


def test_no_ai_filters_and_browse_respect_original_content_constraints(library,monkeypatch):
    client,uid,other,add=library
    add('offline',text='Docker works without cloud services.')
    add('cloud',text='Docker requires a cloud server.')
    def forbidden(*args,**kwargs): raise AssertionError('No AI')
    monkeypatch.setattr(ai_client,'call_provider_model',forbidden)
    body={'query':'Docker without cloud','filters':{'sources':['github.com']},'synthesize':False}
    result=client.post('/api/memory/browse',json=body).json()
    assert [row['id'] for row in result['items']]==['offline']
    assert client.post('/api/memory/filters/interpret',json=body).json()['status']=='local'


def test_ai_calendar_plan_is_bounded_visible_and_preserves_selected_source(library,monkeypatch):
    client,uid,other,add=library
    add('known')
    monkeypatch.setattr(database,'get_ai_assignment_for_feature',lambda *_:{'provider_id':'stub','model':'stub'})
    monkeypatch.setattr(database,'get_ai_provider',lambda *_:{'id':'stub'})
    calls=[]
    def plan(*args,**kwargs):
        calls.append(kwargs)
        return json.dumps({'filters':{'period':'custom','start_date':'2026-11-09','end_date':'2026-11-15'},'phrases':['ko saglabāju pagājušajā nedēļā']})
    monkeypatch.setattr(ai_client,'call_provider_model',plan)
    body={'query':'Parādi visu info par Docker ko saglabāju pagājušajā nedēļā','filters':{'sources':['github.com']},'timezone':'Europe/Riga'}
    result=client.post('/api/memory/filters/interpret',json=body).json()
    assert result['status']=='ai'
    assert result['filters']['sources']==['github.com']
    context=prepare_filter_context(body['query'],result['filters'],'Europe/Riga',False,phrases=result['filter_phrases'])
    assert context['search_text']=='Docker'
    assert calls==[{'timeout':8,'raise_errors':True}]
    monkeypatch.setattr(ai_client,'call_provider_model',lambda *_a,**_k:json.dumps({'filters':{'period':'today'},'phrases':[body['query']]}))
    rejected=client.post('/api/memory/filters/interpret',json=body).json()
    assert rejected['status']=='unavailable' and rejected['filters']['period']=='any'


@pytest.mark.parametrize('url',['/api/memory/query','/api/memory/query/stream','/api/memory/browse','/api/memory/filters/interpret'])
def test_invalid_filters_and_timezones_fail_before_stream_headers(library,url):
    client,uid,other,add=library
    for body in ({'query':'Docker','timezone':'No/Such_Zone'}, {'query':'Docker','filters':{'period':'custom'}}, {'query':'Docker','filters':{'sources':["github.com' OR 1=1"]}}):
        assert client.post(url,json=body).status_code==422


def test_filter_routes_require_member_authentication():
    client=TestClient(main.app)
    assert client.get('/api/memory/filters').status_code==401
    for url in ('/api/memory/browse','/api/memory/filters/interpret'):
        assert client.post(url,json={'query':'Docker'}).status_code==401
    client.close()


def test_ambiguous_or_quoted_dates_are_not_guessed():
    context=prepare_filter_context('Docker yesterday today',now=NOW)
    assert context['filters']['period']=='any'
    assert context['search_text']=='Docker yesterday today'
    assert not prepare_filter_context('Docker "last week"',now=NOW)['needs_ai']
    assert not prepare_filter_context('Docker not last week',now=NOW)['needs_ai']
    with pytest.raises(ValidationError):
        SearchFilters.model_validate({'period':'custom','end_date':'9999-12-31'})


@pytest.mark.parametrize('version',[None,1,2])
def test_ai_search_expansion_cannot_escape_selected_source(library,monkeypatch,version):
    client,uid,other,add=library
    wanted=add('translated-allowed')
    add('translated-excluded',domain='youtube.com')
    monkeypatch.setattr(memory_retrieval,'get_ai_assignment_for_feature',lambda *_:{'provider_id':'stub','model':'stub'})
    monkeypatch.setattr(memory_retrieval,'get_ai_provider',lambda *_:{'id':'stub'})
    monkeypatch.setattr(memory_retrieval,'provider_search_queries',lambda *_a,**_k:['konteineri','Docker'])
    monkeypatch.setattr(memory_retrieval,'_ai_synthesis',lambda *_a,**_k:{'status':'success','view':'list','summary':'Docker','sections':[]})
    monkeypatch.setattr(memory_retrieval,'stream_provider_model',lambda *_a,**_k:iter([f'VIEW: list\nTITLE: Docker\nSUMMARY: Saved Docker.\nSECTION: Docker\nCONTENT: Saved Docker.\nEVIDENCE: {wanted}\n']))
    body={'query':'konteineri','filters':{'sources':['github.com']}}
    url='/api/memory/query'
    if version: url+='/stream'; body['stream_version']=version
    response=client.post(url,json=body)
    assert response.status_code==200,response.text
    result=response.json() if not version else json.loads(response.text.splitlines()[-1])['data']
    if version==2: result=result['result']
    assert [row['id'] for row in result['items']]==[wanted]


def test_cache_keys_include_resolved_filter_scope():
    from app.services.recall_cache import cache_key
    args=('Docker',[],1,{}, {},'auto','auto')
    assert cache_key(*args,filters={'sources':['github.com']}) != cache_key(*args,filters={'sources':['youtube.com']})
