from app.api.routes.search import _extract_suggestions


def test_duckduckgo_suggestions_are_normalized_and_deduplicated():
    payload = [
        {"phrase": "nodecast memory"},
        {"phrase": "Nodecast Memory"},
        {"phrase": "nodecast extension"},
    ]
    assert _extract_suggestions("duckduckgo", payload) == [
        "nodecast memory",
        "nodecast extension",
    ]


def test_duckduckgo_osjson_payload_is_supported():
    assert _extract_suggestions("duckduckgo", ["pancake", ["pancakes", "pancake recipe"]]) == [
        "pancakes",
        "pancake recipe",
    ]


def test_osjson_suggestions_are_bounded():
    payload = ["nodecast", [f"nodecast {index}" for index in range(12)]]
    result = _extract_suggestions("google", payload)
    assert len(result) == 8
    assert result[0] == "nodecast 0"


def test_unknown_payload_returns_empty_list():
    assert _extract_suggestions("unknown", {"items": ["x"]}) == []
