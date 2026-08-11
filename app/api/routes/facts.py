from fastapi import APIRouter, Depends, Query
from app.services.auth import get_current_user
from app.services.database import get_facts_by_topic

router = APIRouter()


@router.get("/api/facts")
def api_facts(
    q: str = Query("", alias="q"),
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    if not q:
        return {"facts": [], "total": 0}
    facts = get_facts_by_topic(current_user["user_id"], q, limit)
    return {"facts": facts, "total": len(facts)}