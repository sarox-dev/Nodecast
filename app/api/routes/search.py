"""
Search API — local search only (web search is handled by redirect in frontend).
"""

from fastapi import APIRouter, Query, Depends
from app.services.database import get_db
from app.services.auth import get_current_user

router = APIRouter()


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