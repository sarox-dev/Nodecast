import json

from app.services import ask_search_plan
from app.services.ask_search_plan import merge_ranked_results, plan_search_queries


def test_original_query_is_preserved_and_alternatives_deduplicated():
    query = "Kādas ir Obsidian alternatīvas?"
    received = []
    def planner(value):
        received.append(value)
        return json.dumps({"queries": ["Obsidian alternatives", "obsidian alternatives", "Logseq Joplin"]})
    assert plan_search_queries(query, planner) == [query, "Obsidian alternatives", "Logseq Joplin"]
    assert received == [query]


def test_sensitive_questions_never_lose_constraints():
    def must_not_call(_):
        raise AssertionError("Sensitive query must not be sent to planner")
    for query in ('rīki bez mākoņa', 'without cloud services', 'GitHub projects after 2025', '"exact phrase"', 'C++'):
        assert plan_search_queries(query, must_not_call) == [query]


def test_invalid_or_failed_plans_fall_back_to_original():
    for raw in ('invalid', '{}', '{"queries": [4]}', '{"queries":["a","b","c","d"]}', '{"queries":["a\\nb"]}'):
        assert plan_search_queries("Obsidian alternatives", lambda _: raw) == ["Obsidian alternatives"]
    assert plan_search_queries("Obsidian alternatives", lambda _: (_ for _ in ()).throw(TimeoutError())) == ["Obsidian alternatives"]


def test_merge_is_bounded_deduplicated_and_preserves_origin():
    a, b, c = {"id":"a", "source_id":"one"}, {"id":"b", "source_id":"two"}, {"id":"c", "source_id":"three"}
    assert merge_ranked_results([[a, b], [a, c]], limit=3) == [a, b, c]
    assert merge_ranked_results([[a]], limit=0) == []


def test_provider_receives_only_the_question_and_has_short_timeout(monkeypatch):
    def fake_provider(user_id, provider, model, messages, **options):
        assert user_id == 'user-a'
        assert json.loads(messages[1]['content']) == {'query': 'Obsidian alternatives'}
        assert options == {'timeout': 8, 'raise_errors': True}
        assert 'English' in messages[0]['content'] and 'original-language' in messages[0]['content']
        return '{"queries":["Joplin notes"]}'
    monkeypatch.setattr(ask_search_plan, 'call_provider_model', fake_provider)
    assert ask_search_plan.provider_search_queries('user-a', {}, 'model', 'Obsidian alternatives') == ['Obsidian alternatives', 'Joplin notes']


def test_diagnostic_status_distinguishes_safety_invalid_and_provider_failure():
    trace = {}
    plan_search_queries('without cloud', lambda _: None, trace)
    assert trace['planner_status'] == 'skipped_sensitive'
    plan_search_queries('Obsidian', lambda _: 'not JSON', trace)
    assert trace['planner_status'] == 'invalid_response'
    plan_search_queries('Obsidian', lambda _: (_ for _ in ()).throw(TimeoutError()), trace)
    assert trace['planner_status'] == 'provider_error'
    plan_search_queries('Obsidian', lambda _: '{"queries":["notes"]}', trace)
    assert trace['planner_status'] == 'success'
