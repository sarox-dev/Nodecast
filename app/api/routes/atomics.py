"""
Atomics API — piekļuve atomics datiem.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.auth import get_current_user
from app.services.database import (
    search_atomics,
    get_atomic_by_id,
    get_atomic_relations,
    insert_atomic,
    insert_atomic_relation,
    delete_atomic,
    get_atomics_by_type,
    get_db,
    enrich_atomics_with_sources,
)
from app.services.atomic_dedup import deduplicate_atomics

router = APIRouter()


@router.get("/api/atomics")
def api_search_atomics(
    q: str = Query(""),
    type: str = Query("", alias="type"),
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    if not q:
        if type:
            atomics = get_atomics_by_type(user_id, type, limit)
        else:
            conn = get_db(user_id)
            try:
                rows = conn.execute(
                    "SELECT * FROM atomics ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                atomics = [dict(r) for r in rows]
            finally:
                conn.close()
        atomics = enrich_atomics_with_sources(user_id, atomics)
        return {"atomics": atomics, "total": len(atomics)}
    atomics = search_atomics(user_id, q, type_=type if type else None, limit=limit)
    atomics = enrich_atomics_with_sources(user_id, atomics)
    return {"atomics": atomics, "total": len(atomics)}


@router.get("/api/atomics/{atomic_id}")
def api_get_atomic(
    atomic_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    atomic = get_atomic_by_id(user_id, atomic_id)
    if not atomic:
        raise HTTPException(404, "Atomic not found")
    enriched = enrich_atomics_with_sources(user_id, [atomic])
    relations = get_atomic_relations(user_id, atomic_id)
    return {"atomic": enriched[0] if enriched else atomic, "relations": relations}


@router.get("/api/atomics/{atomic_id}/children")
def api_get_atomic_children(
    atomic_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return child atomics of an aggregate/hierarchical atomic."""
    user_id = current_user["user_id"]
    atomic = get_atomic_by_id(user_id, atomic_id)
    if not atomic:
        raise HTTPException(404, "Atomic not found")
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            """SELECT a.* FROM atomics a
               JOIN atomic_relations ar ON a.id = ar.target_atomic_id
               WHERE ar.source_atomic_id=? AND ar.relation_type IN ('child_of', 'part_of')
               ORDER BY a.position ASC, a.created_at ASC""",
            (atomic_id,),
        ).fetchall()
        children = [dict(r) for r in rows]
    finally:
        conn.close()
    children = enrich_atomics_with_sources(user_id, children)
    return {"atomic_id": atomic_id, "children": children, "count": len(children)}


@router.delete("/api/atomics/{atomic_id}")
def api_delete_atomic(
    atomic_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not delete_atomic(current_user["user_id"], atomic_id):
        raise HTTPException(404, "Atomic not found")
    return {"success": True, "id": atomic_id}


@router.post("/api/atomics/dedup")
def api_dedup_atomics(
    current_user: dict = Depends(get_current_user),
):
    """Merge duplicate atomics with identical content."""
    result = deduplicate_atomics(current_user["user_id"])
    return {"success": True, "result": result}