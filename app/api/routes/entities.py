from fastapi import APIRouter, Depends, Query, HTTPException
from app.services.auth import get_current_user
from app.services.database import list_entities, get_entity_with_captures

router = APIRouter()


@router.get("/api/entities")
def api_list_entities(
    search: str = "",
    type: str = Query("", alias="type"),
    sort: str = "capture_count",
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    result = list_entities(
        user_id=current_user["user_id"],
        search=search,
        type_filter=type,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return result


@router.get("/api/entity/{entity_id}")
def api_get_entity(
    entity_id: str,
    current_user: dict = Depends(get_current_user),
):
    result = get_entity_with_captures(current_user["user_id"], entity_id)
    if not result:
        raise HTTPException(404, "Entity not found")
    return result