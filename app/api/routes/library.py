import json
from fastapi import APIRouter, Depends
from app.services.auth import get_current_user
from app.services.database import (
    get_db,
    count_captures,
    count_entities,
    count_projects,
    count_tags,
    count_facts,
    get_top_tags,
    get_top_entities,
)
from app.api.routes.search import _to_item, _captures_query

router = APIRouter()


@router.get("/api/library")
def api_library(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    stats = {
        "captures": count_captures(user_id),
        "entities": count_entities(user_id),
        "projects": count_projects(user_id),
        "tags": count_tags(user_id),
        "facts": count_facts(user_id),
    }
    conn = get_db(user_id)
    try:
        recent_rows = conn.execute(
            _captures_query(with_summary=True) + " ORDER BY c.saved_at DESC LIMIT 5"
        ).fetchall()
        recent = [_to_item(r) for r in recent_rows]
    finally:
        conn.close()

    top_tags = get_top_tags(user_id, limit=10)
    top_entities = get_top_entities(user_id, limit=10)

    return {
        "stats": stats,
        "recent": recent,
        "top_tags": top_tags,
        "top_entities": top_entities,
    }