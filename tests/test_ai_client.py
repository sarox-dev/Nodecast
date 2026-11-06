import json
import pytest
import httpx

from app.services import ai_client, database


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    def iter_lines(self):
        for line in self._lines:
            if isinstance(line, Exception):
                raise line
            yield line

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _capture_stream(monkeypatch, lines):
    captured = {}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def stream(self, method, url, json=None, headers=None):
            captured.update(method=method, url=url, payload=json, headers=headers)
            return _FakeResponse(lines)

    monkeypatch.setattr(ai_client.httpx, "Client", FakeClient)
    monkeypatch.setattr(ai_client, "validate_provider_destination", lambda url, *_args, **_kwargs: url)
    monkeypatch.setattr(ai_client, "decrypt_api_key", lambda _value: "secret")
    monkeypatch.setattr(database, "get_user_by_id", lambda _user_id: {"is_admin": True})
    return captured


def test_anthropic_provider_uses_native_messages_stream(monkeypatch):
    captured = _capture_stream(monkeypatch, [
        "event: content_block_delta",
        "data: " + json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}),
        'data: {"type":"message_stop"}',
    ])
    provider = {"base_url": "https://api.anthropic.com/v1", "provider_key": "anthropic", "api_style": "anthropic", "api_key_encrypted": "cipher"}
    result = list(ai_client.stream_provider_model("user-a", provider, "claude-test", [
        {"role": "system", "content": "Be concise."}, {"role": "user", "content": "Hi"},
    ]))

    assert result == ["Hello"]
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "secret"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["payload"]["system"] == "Be concise."
    assert captured["payload"]["messages"] == [{"role": "user", "content": "Hi"}]


def test_gemini_provider_uses_native_content_stream(monkeypatch):
    captured = _capture_stream(monkeypatch, [
        "data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "Sveiki"}]}, "finishReason": "STOP"}]}),
    ])
    provider = {"base_url": "https://generativelanguage.googleapis.com/v1beta", "provider_key": "gemini", "api_style": "gemini", "api_key_encrypted": "cipher"}
    result = list(ai_client.stream_provider_model("user-a", provider, "gemini-test", [
        {"role": "system", "content": "Atbildi latviski."}, {"role": "user", "content": "Sveiki"},
    ]))

    assert result == ["Sveiki"]
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:streamGenerateContent?alt=sse"
    assert captured["headers"]["x-goog-api-key"] == "secret"
    assert captured["payload"]["systemInstruction"] == {"parts": [{"text": "Atbildi latviski."}]}
    assert captured["payload"]["contents"] == [{"role": "user", "parts": [{"text": "Sveiki"}]}]


def test_openai_compatible_provider_keeps_chat_completion_stream(monkeypatch):
    captured = _capture_stream(monkeypatch, [
        "data: " + json.dumps({"choices": [{"delta": {"content": "token"}}]}),
        "data: [DONE]",
    ])
    provider = {"base_url": "https://provider.example/v1", "provider_key": "openai", "api_style": "openai", "api_key_encrypted": "cipher"}
    result = list(ai_client.stream_provider_model("user-a", provider, "model-a", [{"role": "user", "content": "Hi"}]))

    assert result == ["token"]
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["payload"]["stream"] is True


@pytest.mark.parametrize("style,event", [
    ("openai", {"choices": [{"delta": {"content": "partial"}}]}),
    ("anthropic", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "partial"}}),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "partial"}]}}]}),
])
def test_truncated_stream_never_returns_partial_success(monkeypatch, style, event):
    _capture_stream(monkeypatch, ["data: " + json.dumps(event)])
    provider = {"base_url": "https://provider.example/v1", "api_style": style}
    with pytest.raises(ai_client.AIClientError) as exc:
        ai_client.call_provider_model("user-a", provider, "model", [], raise_errors=True)
    assert exc.value.code == "ai_stream_incomplete"
    assert ai_client.call_provider_model("user-a", provider, "model", []) is None


@pytest.mark.parametrize("style,event", [
    ("openai", {"error": {"message": "failure"}}),
    ("anthropic", {"type": "error", "error": {"type": "overloaded_error"}}),
    ("gemini", {"error": {"code": 503}}),
    ("gemini", {"promptFeedback": {"blockReason": "SAFETY"}}),
])
def test_provider_error_event_is_not_silent_success(monkeypatch, style, event):
    _capture_stream(monkeypatch, ["data: " + json.dumps(event)])
    provider = {"base_url": "https://provider.example/v1", "api_style": style}
    with pytest.raises(ai_client.AIClientError):
        list(ai_client.stream_provider_model("user-a", provider, "model", []))


@pytest.mark.parametrize("failure,code", [
    (httpx.ReadTimeout("timeout"), "ai_timeout"),
    (httpx.RemoteProtocolError("disconnected"), "ai_provider_error"),
    (ValueError("malformed"), "ai_provider_error"),
])
def test_transport_failure_discards_partial_result(monkeypatch, failure, code):
    _capture_stream(monkeypatch, ['data: {"choices":[{"delta":{"content":"partial"}}]}', failure])
    provider = {"base_url": "https://provider.example/v1", "api_style": "openai"}
    with pytest.raises(ai_client.AIClientError) as exc:
        ai_client.call_provider_model("user-a", provider, "model", [], raise_errors=True)
    assert exc.value.code == code
    assert ai_client.call_provider_model("user-a", provider, "model", []) is None


@pytest.mark.parametrize("style,event", [
    ("openai", {"choices": [{"delta": {}, "finish_reason": "length"}]}),
    ("anthropic", {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}),
    ("gemini", {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
])
def test_output_limit_is_not_success(monkeypatch, style, event):
    _capture_stream(monkeypatch, ["data: " + json.dumps(event)])
    with pytest.raises(ai_client.AIClientError):
        list(ai_client.stream_provider_model("user-a", {"base_url": "https://provider.example/v1", "api_style": style}, "model", []))
