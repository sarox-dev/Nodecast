"""
Entity API — rewritten to use atomics(type=entity) instead of old entities table.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from app.services.auth import get_current_user
from app.services.database import (
    get_db,
    enrich_atomics_with_sources,
    get_atomic_relations,
)

router = APIRouter()


@router.get("/api/entities")
def api_list_entities(
    search: str = "",
    type: str = Query("", alias="type"),
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        where = ["a.type='entity'"]
        params = []
        if search:
            where.append("a.content LIKE ?")
            params.append(f"%{search}%")
        if type:
            where.append("json_extract(a.properties, '$.entity_type')=?")
            params.append(type)
        where_clause = " AND ".join(where)

        # Count related atomics per entity
        rows = conn.execute(
            f"""SELECT a.id, a.content, a.properties,
                       (SELECT COUNT(*) FROM atomic_relations ar WHERE ar.source_atomic_id=a.id AND ar.relation_type='references') as ref_count
                FROM atomics a
                WHERE {where_clause}
                ORDER BY {'a.content ASC' if sort == 'name' else 'ref_count DESC'}
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

        count = conn.execute(
            f"SELECT COUNT(*) as cnt FROM atomics a WHERE {where_clause}", params
        ).fetchone()

        result = []
        for r in rows:
            props = {}
            if isinstance(r["properties"], str):
                import json
                try:
                    props = json.loads(r["properties"])
                except (json.JSONDecodeError, TypeError):
                    props = {}
            result.append({
                "id": r["id"],
                "name": r["content"],
                "type": props.get("entity_type", "concept"),
                "aliases": props.get("aliases", []),
                "description": props.get("description", ""),
                "capture_count": r["ref_count"],
            })

        return {"entities": result, "total": count["cnt"] if count else 0}
    finally:
        conn.close()


@router.get("/api/entity/{entity_id}")
def api_get_entity(
    entity_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        row = conn.execute(
            "SELECT * FROM atomics WHERE id=? AND type='entity'",
            (entity_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, "Entity not found")

    entity = dict(row)
    if isinstance(entity.get("properties"), str):
        import json
        try:
            entity["properties"] = json.loads(entity["properties"])
        except (json.JSONDecodeError, TypeError):
            entity["properties"] = {}

    # Get related atomics (references from this entity)
    relations = get_atomic_relations(user_id, entity_id)
    target_ids = []
    for r in relations:
        if r["relation_type"] == "references" and r["source_atomic_id"] == entity_id:
            target_ids.append(r["target_atomic_id"])

    # Get source captures from those atomics
    conn = get_db(user_id)
    try:
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            atomics = conn.execute(
                f"SELECT a.id, a.type, a.content, a.source_id, c.source_url, c.source_title, c.source_site_name FROM atomics a LEFT JOIN captures c ON a.source_id=c.id WHERE a.id IN ({placeholders})",
                target_ids,
            ).fetchall()
            captures = []
            related_atomics = []
            seen_sources = set()
            for a in atomics:
                related_atomics.append({
                    "id": a["id"],
                    "type": a["type"],
                    "content": a["content"] or "",
                    "source_url": a["source_url"] or "",
                    "source_title": a["source_title"] or "",
                    "source_site_name": a["source_site_name"] or "",
                })
                src_id = a["source_id"]
                if src_id and src_id not in seen_sources:
                    seen_sources.add(src_id)
                    captures.append({
                        "id": src_id,
                        "source_title": a["source_title"] or "",
                        "source_url": a["source_url"] or "",
                        "source_site_name": a["source_site_name"] or "",
                    })
        else:
            related_atomics = []
            captures = []
    finally:
        conn.close()

    return {
        "entity": {
            "id": entity["id"],
            "name": entity["content"],
            "type": entity["properties"].get("entity_type", "concept"),
            "aliases": entity["properties"].get("aliases", []),
            "description": entity["properties"].get("description", ""),
            "capture_count": len(captures),
        },
        "captures": captures,
        "related_atomics": related_atomics,
        "related_entities": [],
    }