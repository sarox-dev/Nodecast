from fastapi import APIRouter, Query
from app.services.searxng import search

router = APIRouter()

@router.get("/search")
def search_route(
    q: str | None = Query(None),
    type: str = Query("web"),
    page: int = Query(1, ge=1),
    count: int = Query(10, ge=1, le=50),
    engines: str | None = Query(None),
):
    if not q:
        return {"message": "use ?q="}

    categories = "images" if type == "images" else "general"

    results = search(q, page, count, engines, categories)

    if results is None:
        return {"error": "search backend unavailable"}

    return results