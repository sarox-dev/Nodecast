"""Search API — local memory plus optional provider query suggestions."""

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query

from app.services.database import get_db
from app.services.auth import get_current_user

router = APIRouter()

SUGGESTION_PROVIDERS = {
    "duckduckgo": ("https://duckduckgo.com/ac/", "q"),
    "google": ("https://suggestqueries.google.com/complete/search", "q"),
    "bing": ("https://api.bing.com/osjson.aspx", "query"),
}


def _extract_suggestions(provider: str, payload: Any) -> list[str]:
    """Normalize public provider payloads without exposing their shape to the UI."""
    values: list[Any] = []
    if provider == "duckduckgo" and isinstance(payload, list):
        if len(payload) > 1 and isinstance(payload[1], list):
            values = payload[1]
        else:
            values = [item.get("phrase") for item in payload if isinstance(item, dict)]
    elif provider in {"google", "bing"} and isinstance(payload, list) and len(payload) > 1:
        values = payload[1] if isinstance(payload[1], list) else []

    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        suggestion = str(value or "").strip()
        key = suggestion.casefold()
        if not suggestion or key in seen:
            continue
        seen.add(key)
        normalized.append(suggestion[:200])
        if len(normalized) == 8:
            break
    return normalized


@router.get("/search")
def search_route(
    q: str | None = Query(None),
    source: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Local search only. For web search, frontend redirects to preferred engine."""
    if not q:
        return {"results": [], "total": 0}
    conn = get_db(current_user["user_id"])
    try:
        rows = conn.execute(
            "SELECT * FROM atomics WHERE content LIKE ? ORDER BY relevance DESC, created_at DESC LIMIT 50",
            (f"%{q}%",),
        ).fetchall()
        results = [dict(r) for r in rows]
    finally:
        conn.close()
    return {"results": results, "total": len(results)}


@router.get("/browse")
def browse_captures(
    current_user: dict = Depends(get_current_user),
):
    conn = get_db(current_user["user_id"])
    try:
        rows = conn.execute(
            "SELECT * FROM atomics ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/api/web/suggestions")
async def web_suggestions(
    q: str = Query("", min_length=0, max_length=200),
    provider: str = Query("duckduckgo"),
    current_user: dict = Depends(get_current_user),
):
    """Proxy opt-in search suggestions so provider CORS differences stay out of the UI."""
    del current_user
    query = q.strip()
    if len(query) < 2 or provider == "none":
        return {"provider": provider, "suggestions": []}
    config = SUGGESTION_PROVIDERS.get(provider)
    if not config:
        return {"provider": provider, "suggestions": []}

    url, query_key = config
    params = {query_key: query}
    if provider == "duckduckgo":
        params["type"] = "list"
    elif provider == "google":
        params["client"] = "firefox"

    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "Nodecast/1.0"})
            response.raise_for_status()
            suggestions = _extract_suggestions(provider, response.json())
    except (httpx.HTTPError, ValueError, TypeError):
        suggestions = []
    return {"provider": provider, "suggestions": suggestions}
