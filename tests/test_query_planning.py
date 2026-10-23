import pytest

from app.services.query_planning import build_query_plan, validate_query_plan


def test_deterministic_plan_understands_latvian_comparison_and_language():
    plan = build_query_plan("Salīdzini Ollama un llama.cpp darbības pieeju")
    assert plan["intent"] == "compare"
    assert plan["query_language"] == "lv"
    assert plan["response_language"] == "lv"
    assert "Latin" in plan["scripts"]


def test_plan_uses_script_fallback_without_language_whitelist():
    plan = build_query_plan("SQLite预写式日志如何支持并发读写？")
    assert plan["query_language"] == "zh-Hans"
    assert "Han" in plan["scripts"]


def test_model_plan_is_untrusted_and_rejects_unsupported_filters():
    with pytest.raises(ValueError):
        validate_query_plan({"intent": "research", "constraints": [{"field": "user_id", "op": "eq", "value": "other"}]})


def test_validated_model_plan_is_bounded():
    plan = validate_query_plan({
        "intent": "research",
        "query_language": "ar",
        "response_language": "ar",
        "entities": ["x" * 200],
        "dimensions": ["security"],
        "alternative_queries": ["q" * 900],
        "constraints": [{"field": "language", "op": "eq", "value": "ar"}],
    })
    assert len(plan["entities"][0]) == 100
    assert len(plan["alternative_queries"][0]) == 500
    assert plan["constraints"][0]["field"] == "language"
