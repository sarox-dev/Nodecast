"""OpenAI-compatible chat client shared by atomic AI services."""
import json
import logging
import httpx

logger = logging.getLogger(__name__)


def call_ai_model(base_url: str, api_key: str, model: str, messages: list[dict], timeout: int = 120) -> str | None:
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
        return None
