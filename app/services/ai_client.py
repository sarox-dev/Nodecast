"""OpenAI-compatible chat client shared by atomic AI services."""
import json
import logging
from urllib.parse import quote
import httpx

from app.services.ai_crypto import decrypt_api_key
from app.services.outbound_security import validate_provider_destination

logger = logging.getLogger(__name__)


class AIClientError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def call_ai_model(base_url: str, api_key: str, model: str, messages: list[dict], timeout: int = 120, raise_errors: bool = False) -> str | None:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1200},
                headers=headers,
            )
            response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning_content") or ""
        if content.strip().startswith("{"):
            try:
                parsed = json.loads(content)
                params = parsed.get("parameters", {}) if isinstance(parsed, dict) else {}
                content = params.get("text") or params.get("summary") or content
            except json.JSONDecodeError:
                pass
        return content.strip() or None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.error("AI request failed for %s: %s", model, exc)
        if raise_errors:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if status in {401, 403}:
                raise AIClientError("ai_authentication_failed", "AI provider authentication failed. Check the API key in Settings → AI.", status) from exc
            if status == 429:
                raise AIClientError("ai_rate_limited", "AI provider rate limit reached. Local results are still available.", status) from exc
            if isinstance(exc, httpx.TimeoutException):
                raise AIClientError("ai_timeout", "AI provider timed out. Local results are still available.") from exc
            raise AIClientError("ai_provider_error", "AI synthesis failed. Local results are still available.", status) from exc
        return None


def _call_chatgpt_plan(user_id: str, provider: dict, model: str, messages: list[dict], timeout: int) -> str:
    """Call Responses API without ChatGPT conversation state or server-side storage."""
    return "".join(_stream_chatgpt_plan(user_id, provider, model, messages, timeout)).strip()


def _stream_chatgpt_plan(user_id: str, provider: dict, model: str, messages: list[dict], timeout: int):
    """Yield isolated Responses API text deltas without ChatGPT conversation state."""
    from app.services.chatgpt_oauth import get_access_token

    instructions = "\n\n".join(
        str(message.get("content", "")) for message in messages if message.get("role") == "system"
    )
    input_messages = [
        {"role": message.get("role", "user"), "content": str(message.get("content", ""))}
        for message in messages if message.get("role") != "system"
    ]
    token = get_access_token(user_id, provider["id"])
    payload = {"model": model, "input": input_messages, "store": False, "stream": True}
    if instructions:
        payload["instructions"] = instructions
    completed = False
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST", "https://api.openai.com/v1/responses", json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                event_type = event.get("type", "")
                if event_type == "response.output_text.delta":
                    yield event.get("delta", "")
                elif event_type == "response.completed":
                    completed = True
                elif event_type == "response.failed":
                    error = (event.get("response") or {}).get("error") or {}
                    raise AIClientError(error.get("code", "chatgpt_plan_failed"), error.get("message", "ChatGPT plan request failed"))
    if not completed:
        raise AIClientError("chatgpt_stream_incomplete", "ChatGPT response stream ended before completion")


def stream_provider_model(user_id: str, provider: dict, model: str, messages: list[dict], timeout: int = 120):
    """Yield text deltas from a provider while preserving Nodecast provider boundaries."""
    if provider.get("provider_type") == "chatgpt_oauth":
        try:
            yield from _stream_chatgpt_plan(user_id, provider, model, messages, timeout)
        except AIClientError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if status in {401, 403}:
                raise AIClientError("chatgpt_reconnect_required", "ChatGPT authorization expired. Reconnect it in Settings → AI.", status) from exc
            if status == 429:
                raise AIClientError("chatgpt_plan_limit", "ChatGPT plan usage limit reached. Local results are still available.", status) from exc
            raise AIClientError("chatgpt_plan_error", "ChatGPT plan request failed. Local results are still available.", status) from exc
        return

    from app.services.database import get_user_by_id

    account = get_user_by_id(user_id)
    base_url = validate_provider_destination(
        provider["base_url"], provider.get("provider_key", ""),
        is_admin=bool(account and account.get("is_admin")),
    )
    headers = {"Content-Type": "application/json"}
    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))
    api_style = provider.get("api_style") or "openai"
    if api_style == "anthropic":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        system = "\n\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        payload = {
            "model": model, "max_tokens": 1200, "stream": True,
            "messages": [{"role": item.get("role", "user"), "content": str(item.get("content", ""))}
                         for item in messages if item.get("role") != "system"],
        }
        if system:
            payload["system"] = system
        url = f"{base_url.rstrip('/')}/messages"
    elif api_style == "gemini":
        headers["x-goog-api-key"] = api_key
        system = "\n\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        payload = {
            "contents": [{
                "role": "model" if item.get("role") == "assistant" else "user",
                "parts": [{"text": str(item.get("content", ""))}],
            } for item in messages if item.get("role") != "system"],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1200},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{base_url.rstrip('/')}/models/{quote(model, safe='')}:streamGenerateContent?alt=sse"
    else:
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1200, "stream": True}
        url = f"{base_url.rstrip('/')}/chat/completions"
    completed = False
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                "POST", url, json=payload, headers=headers,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        if api_style not in {"anthropic", "gemini"}:
                            completed = True
                        continue
                    if not data:
                        continue
                    event = json.loads(data)
                    if event.get("error") or event.get("type") == "error":
                        raise AIClientError("ai_provider_error", "AI provider returned a stream error. Local results are still available.")
                    if api_style == "anthropic":
                        if event.get("type") == "message_stop":
                            completed = True
                        if (event.get("delta") or {}).get("stop_reason") == "max_tokens":
                            raise AIClientError("ai_output_truncated", "AI output exceeded the provider token limit.")
                        delta = event.get("delta") or {}
                        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                            if delta.get("text"):
                                yield delta["text"]
                    elif api_style == "gemini":
                        if (event.get("promptFeedback") or {}).get("blockReason"):
                            raise AIClientError("ai_content_blocked", "AI provider blocked the request.")
                        candidates = event.get("candidates") or []
                        reason = candidates[0].get("finishReason") if candidates else None
                        if reason and reason != "STOP":
                            raise AIClientError("ai_output_incomplete", "AI provider did not finish the answer successfully.")
                        if reason == "STOP":
                            completed = True
                        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
                        for part in parts:
                            if part.get("text"):
                                yield part["text"]
                    else:
                        choices = event.get("choices") or []
                        if choices:
                            reason = choices[0].get("finish_reason")
                            if reason and reason != "stop":
                                raise AIClientError("ai_output_incomplete", "AI provider did not finish the answer successfully.")
                            delta = (choices[0].get("delta") or {}).get("content") or ""
                            if delta:
                                yield delta
        if not completed:
            raise AIClientError("ai_stream_incomplete", "AI response stream ended before completion. Local results are still available.")
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        if status in {401, 403}:
            raise AIClientError("ai_authentication_failed", "AI provider authentication failed. Check the API key in Settings → AI.", status) from exc
        if status == 429:
            raise AIClientError("ai_rate_limited", "AI provider rate limit reached. Local results are still available.", status) from exc
        if isinstance(exc, httpx.TimeoutException):
            raise AIClientError("ai_timeout", "AI provider timed out. Local results are still available.") from exc
        raise AIClientError("ai_provider_error", "AI synthesis failed. Local results are still available.", status) from exc


def call_provider_model(user_id: str, provider: dict, model: str, messages: list[dict], timeout: int = 120, raise_errors: bool = False) -> str | None:
    """Dispatch through the provider contract, including isolated ChatGPT plan OAuth."""
    try:
        return "".join(stream_provider_model(user_id, provider, model, messages, timeout)).strip() or None
    except AIClientError:
        if raise_errors:
            raise
        return None
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.error("AI provider request failed for %s: %s", model, exc)
        if raise_errors:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            raise AIClientError("ai_provider_error", "AI provider request failed. Local results are still available.", status) from exc
        return None
