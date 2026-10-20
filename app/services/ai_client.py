"""OpenAI-compatible chat client shared by atomic AI services."""
import json
import logging
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
    output = []
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
                    output.append(event.get("delta", ""))
                elif event_type == "response.completed":
                    completed = True
                elif event_type == "response.failed":
                    error = (event.get("response") or {}).get("error") or {}
                    raise AIClientError(error.get("code", "chatgpt_plan_failed"), error.get("message", "ChatGPT plan request failed"))
    if not completed:
        raise AIClientError("chatgpt_stream_incomplete", "ChatGPT response stream ended before completion")
    return "".join(output).strip()


def call_provider_model(user_id: str, provider: dict, model: str, messages: list[dict], timeout: int = 120, raise_errors: bool = False) -> str | None:
    """Dispatch through the provider contract, including isolated ChatGPT plan OAuth."""
    if provider.get("provider_type") != "chatgpt_oauth":
        from app.services.database import get_user_by_id

        account = get_user_by_id(user_id)
        base_url = validate_provider_destination(
            provider["base_url"],
            provider.get("provider_key", ""),
            is_admin=bool(account and account.get("is_admin")),
        )
        return call_ai_model(
            base_url, decrypt_api_key(provider.get("api_key_encrypted", "")),
            model, messages, timeout=timeout, raise_errors=raise_errors,
        )
    try:
        return _call_chatgpt_plan(user_id, provider, model, messages, timeout) or None
    except AIClientError:
        if raise_errors:
            raise
        return None
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.error("ChatGPT plan request failed for %s: %s", model, exc)
        if raise_errors:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if status in {401, 403}:
                raise AIClientError("chatgpt_reconnect_required", "ChatGPT authorization expired. Reconnect it in Settings → AI.", status) from exc
            if status == 429:
                raise AIClientError("chatgpt_plan_limit", "ChatGPT plan usage limit reached. Local results are still available.", status) from exc
            raise AIClientError("chatgpt_plan_error", "ChatGPT plan request failed. Local results are still available.", status) from exc
        return None
