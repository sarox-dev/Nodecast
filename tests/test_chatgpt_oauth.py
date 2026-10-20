import json
from urllib.parse import parse_qs, urlparse

from app.services import ai_client, chatgpt_oauth
from app.api.routes.ai_providers import _normalize_model_catalog


def test_authorization_uses_pkce_and_plan_scopes(monkeypatch):
    saved = {}
    monkeypatch.setattr(chatgpt_oauth, "get_or_create_host_id", lambda: "urn:uuid:test-host")
    monkeypatch.setattr(chatgpt_oauth, "create_ai_oauth_transaction", lambda *args: saved.setdefault("args", args))
    url = chatgpt_oauth.begin_authorization("user-a", "http://127.0.0.1:5000/api/ai/chatgpt/callback")
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["dynamic_agent_client"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["resource"] == ["https://api.openai.com/v1"]
    assert "chatgpt.tokens.use.direct" in query["scope"][0]
    assert saved["args"][0] == query["state"][0]


def test_chatgpt_plan_request_is_isolated_and_not_stored(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def iter_lines(self):
            yield "data: " + json.dumps({"type": "response.output_text.delta", "delta": "saved evidence"})
            yield "data: " + json.dumps({"type": "response.completed"})
        def __enter__(self): return self
        def __exit__(self, *_): return False

    class FakeClient:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def stream(self, method, url, json=None, headers=None):
            captured.update({"method": method, "url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(chatgpt_oauth, "get_access_token", lambda *_: "oauth-token")
    monkeypatch.setattr(ai_client.httpx, "Client", FakeClient)
    result = ai_client._call_chatgpt_plan("user-a", {"id": "provider-a"}, "model-a", [
        {"role": "system", "content": "Use only supplied evidence."},
        {"role": "user", "content": "Nodecast evidence packet"},
    ], 30)
    assert result == "saved evidence"
    assert captured["json"]["store"] is False
    assert captured["json"]["stream"] is True
    assert captured["json"]["instructions"] == "Use only supplied evidence."
    assert captured["json"]["input"] == [{"role": "user", "content": "Nodecast evidence packet"}]
    assert "previous_response_id" not in captured["json"]
    assert "conversation" not in captured["json"]


def test_chatgpt_model_catalog_uses_visible_slugs_and_display_names():
    models = _normalize_model_catalog({"models": [
        {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1-Sol", "visibility": "list"},
        {"slug": "internal-model", "display_name": "Internal", "visibility": "hidden"},
    ]}, chatgpt_plan=True)
    assert models == [{"id": "gpt-6.1-sol", "name": "GPT-6.1-Sol", "object": "model"}]
