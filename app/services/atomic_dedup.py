"""
Atomic Deduplication Service — merge atomics with identical content.
Run as maintenance: deduplicate_atomics(user_id)
"""

import json
import logging
from uuid import uuid4

from app.services.database import get_db

logger = logging.getLogger(__name__)


def deduplicate_atomics(user_id: str) -> dict:
    """Find atomics with identical content, merge them, delete duplicates.
    Returns stats: {removed: N, kept: N, groups: N}"""
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            "SELECT id, type, content, source_id, source_atomics FROM atomics WHERE type != 'entity' ORDER BY type, content, created_at ASC"
        ).fetchall()
    finally:
        conn.close()

    # Group by (type, content)
    groups: dict[tuple[str, str, str | None], list[dict]] = {}
    for r in rows:
        d = dict(r)
        # Identical text from different sources is corroboration, not a duplicate.
        key = (d["type"], d["content"].strip(), d["source_id"])
        groups.setdefault(key, []).append(d)

    removed = 0
    kept = 0
    groups_found = 0

    for (type_, content, source_id), items in groups.items():
        if len(items) <= 1:
            continue
        groups_found += 1
        # Keep the first one (oldest), remove the rest
        keep = items[0]
        removed_before = removed
        for dup in items[1:]:
            if _merge_atomic(user_id, keep["id"], dup["id"]):
                removed += 1
        if removed > removed_before:
            kept += 1

    return {"removed": removed, "kept": kept, "groups": groups_found}


def _merge_atomic(user_id: str, keep_id: str, remove_id: str) -> bool:
    """Move all relations from remove_id to keep_id, then delete remove_id."""
    conn = get_db(user_id)
    try:
        relations = conn.execute(
            "SELECT * FROM atomic_relations WHERE source_atomic_id=? OR target_atomic_id=?",
            (remove_id, remove_id),
        ).fetchall()
        for relation in relations:
            source_id = keep_id if relation["source_atomic_id"] == remove_id else relation["source_atomic_id"]
            target_id = keep_id if relation["target_atomic_id"] == remove_id else relation["target_atomic_id"]
            if source_id != target_id:
                conn.execute(
                    """INSERT INTO atomic_relations
                       (id,source_atomic_id,target_atomic_id,relation_type,strength,context,created_at)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(source_atomic_id,target_atomic_id,relation_type)
                       DO UPDATE SET strength=MAX(strength,excluded.strength),context=excluded.context""",
                    (
                        uuid4().hex[:16], source_id, target_id, relation["relation_type"],
                        relation["strength"], relation["context"], relation["created_at"],
                    ),
                )
            conn.execute("DELETE FROM atomic_relations WHERE id=?", (relation["id"],))
        # Delete the duplicate
        conn.execute("DELETE FROM atomics WHERE id=?", (remove_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.warning("Merge atomic %s → %s failed: %s", remove_id, keep_id, e)
        return False
    finally:
        conn.close()
