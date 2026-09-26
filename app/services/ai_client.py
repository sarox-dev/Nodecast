"""OpenAI-compatible chat client shared by atomic AI services."""
import json
import logging
import httpx

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
