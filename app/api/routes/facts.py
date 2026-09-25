from fastapi import APIRouter, Depends, Query
from app.services.auth import get_current_user
from app.services.database import get_atomics_by_type, search_atomics, enrich_atomics_with_sources

router = APIRouter()


@router.get("/api/facts")
def api_facts(
    q: str = Query("", alias="q"),
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    facts = search_atomics(user_id, q, type_="fact", limit=limit) if q else get_atomics_by_type(user_id, "fact", limit)
    facts = enrich_atomics_with_sources(user_id, facts)
    return {"facts": facts, "total": len(facts)}
