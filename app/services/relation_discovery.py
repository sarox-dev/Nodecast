"""
Relation Discovery Service — Stage 1: deterministic candidate matching
based on shared tags and entities (0 AI tokens).

Uses Jaccard similarity to find related captures and creates `related_to`
relations with strength = combined_score. Also discovers entity↔entity
connections via shared captures.

Stage 2 (AI connection typing) will be added separately.
"""

import json
import logging
from datetime import datetime, timezone

from app.services.database import (
    get_db,
    insert_relation,
    delete_relations_for_capture,
    RELATION_TYPES,
)

logger = logging.getLogger(__name__)

FEATURE_RELATION_DISCOVERY = "relation_discovery"

# ─── Scoring constants ──────────────────────────────────────────────

TAG_WEIGHT = 0.3
ENTITY_WEIGHT = 0.7
MAX_CANDIDATES = 25
MIN_STRENGTH = 0.01  # any overlap at all

# ─── Helpers ────────────────────────────────────────────────────────


def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity between two sets. Returns 0.0 if both empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _get_capture_tags(user_id: str, capture_id: str) -> set[str]:
    """Get the AI tags (from capture_ai_tags) or manual tags (from captures) for a capture."""
    conn = get_db(user_id)
    try:
        # Try AI tags first
        row = conn.execute(
            "SELECT tags FROM capture_ai_tags WHERE capture_id=?", (capture_id,)
        ).fetchone()
        if row and row["tags"]:
            tags = json.loads(row["tags"])
            if isinstance(tags, list) and tags:
                return set(t.lower().strip() for t in tags if t.strip())

        # Fall back to manual tags from captures table
        row = conn.execute(
            "SELECT tags FROM captures WHERE id=?", (capture_id,)
        ).fetchone()
        if row and row["tags"]:
            tags = json.loads(row["tags"])
            if isinstance(tags, list):
                return set(t.lower().strip() for t in tags if t.strip())
        return set()
    finally:
        conn.close()


def _get_capture_entity_names(user_id: str, capture_id: str) -> set[str]:
    """Get the names of all entities linked to this capture."""
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            """SELECT e.name FROM entities e
               JOIN capture_entities ce ON e.id = ce.entity_id
               WHERE ce.capture_id=?""",
            (capture_id,),
        ).fetchall()
        return set(r["name"].lower().strip() for r in rows if r["name"])
    finally:
        conn.close()


def _get_all_capture_ids(user_id: str) -> list[str]:
    """Get all capture IDs for this user."""
    conn = get_db(user_id)
    try:
        rows = conn.execute("SELECT id FROM captures ORDER BY saved_at DESC").fetchall()
        return [r["id"] for r in rows]
    finally:
        conn.close()


# ─── Candidate discovery ────────────────────────────────────────────


def find_relation_candidates(
    user_id: str, capture_id: str
) -> list[tuple[str, float, set[str], set[str]]]:
    """Find top candidates for a capture based on shared tags and entities.

    Returns list of (candidate_capture_id, combined_score, shared_tags, shared_entities)
    sorted by score descending, limited to MAX_CANDIDATES.
    """
    source_tags = _get_capture_tags(user_id, capture_id)
    source_entities = _get_capture_entity_names(user_id, capture_id)

    if not source_tags and not source_entities:
        logger.info(
            "No tags or entities for capture %s — no candidates possible",
            capture_id,
        )
        return []

    all_ids = _get_all_capture_ids(user_id)
    candidates = []

    for cid in all_ids:
        if cid == capture_id:
            continue

        target_tags = _get_capture_tags(user_id, cid)
        target_entities = _get_capture_entity_names(user_id, cid)

        if not target_tags and not target_entities:
            continue

        tag_jaccard = _jaccard(source_tags, target_tags)
        entity_jaccard = _jaccard(source_entities, target_entities)
        combined = TAG_WEIGHT * tag_jaccard + ENTITY_WEIGHT * entity_jaccard

        if combined < MIN_STRENGTH:
            continue

        # Record what they share for context
        shared_tags = source_tags & target_tags
        shared_entities = source_entities & target_entities

        candidates.append((cid, combined, shared_tags, shared_entities))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:MAX_CANDIDATES]


# ─── Entity-entity discovery ────────────────────────────────────────


def discover_entity_relations(user_id: str) -> int:
    """Find entity↔entity relations based on shared captures.

    For every pair of entities that appear together in at least one capture,
    create a `related_to` relation. Strength = overlap / total captures of the
    less-common entity (co-occurrence ratio).

    Returns number of relations created/updated.
    """
    conn = get_db(user_id)
    try:
        # Get entity → captures mapping
        rows = conn.execute(
            """SELECT entity_id, capture_id FROM capture_entities
               ORDER BY entity_id"""
        ).fetchall()
    finally:
        conn.close()

    # Build entity → set of captures
    entity_captures: dict[str, set[str]] = {}
    for r in rows:
        eid = r["entity_id"]
        cid = r["capture_id"]
        entity_captures.setdefault(eid, set()).add(cid)

    entity_ids = list(entity_captures.keys())
    if len(entity_ids) < 2:
        return 0

    created = 0
    for i in range(len(entity_ids)):
        e1 = entity_ids[i]
        caps1 = entity_captures[e1]
        for j in range(i + 1, len(entity_ids)):
            e2 = entity_ids[j]
            caps2 = entity_captures[e2]
            overlap = caps1 & caps2
            if not overlap:
                continue
            # Strength based on how many captures they share vs total of the less common one
            total = min(len(caps1), len(caps2))
            strength = len(overlap) / total if total > 0 else 0.0
            if strength < 0.05:
                continue  # too weak

            context = f"Shared in {len(overlap)} capture(s)"
            insert_relation(
                user_id=user_id,
                source_type="entity",
                source_id=e1,
                target_type="entity",
                target_id=e2,
                relation_type="related_to",
                strength=strength,
                context=context,
            )
            created += 1

    return created


# ─── Main discover function ─────────────────────────────────────────


def discover_relations(user_id: str, capture_id: str) -> dict:
    """Run Stage 1 deterministic relation discovery for a single capture.

    Steps:
    1. Find top candidates by shared tags/entities
    2. Insert related_to relations for each candidate
    3. (Optionally) run entity↔entity discovery (heavy, done separately)

    Returns dict with status and count.
    """
    # Clear old relations involving this capture (they'll be replaced)
    delete_relations_for_capture(user_id, capture_id)

    # Find candidates
    candidates = find_relation_candidates(user_id, capture_id)
    if not candidates:
        logger.info(
            "No candidates found for capture %s", capture_id
        )
        return {"status": "success", "candidate_count": 0, "relations_created": 0}

    # For each candidate capture, also look up its title for context
    conn = get_db(user_id)
    try:
        title_map = {
            r["id"]: r["source_title"] or ""
            for r in conn.execute(
                "SELECT id, source_title FROM captures WHERE id IN ({})".format(
                    ",".join("?" for _ in [c[0] for c in candidates])
                ),
                [c[0] for c in candidates],
            ).fetchall()
        }
    finally:
        conn.close()

    created = 0
    for cid, score, shared_tags, shared_entities in candidates:
        # Build a meaningful context string
        context_parts = []
        if shared_tags:
            context_parts.append(f"shared tags: {', '.join(sorted(shared_tags)[:5])}")
        if shared_entities:
            context_parts.append(f"shared entities: {', '.join(sorted(shared_entities)[:5])}")

        # Also show the other capture's title for context
        other_title = title_map.get(cid, "")
        context = f"Related to \"{other_title}\". " if other_title else ""
        context += "; ".join(context_parts)

        insert_relation(
            user_id=user_id,
            source_type="capture",
            source_id=capture_id,
            target_type="capture",
            target_id=cid,
            relation_type="related_to",
            strength=round(score, 4),
            context=context,
        )
        created += 1

    logger.info(
        "Discovered %d relations for capture %s (%d candidates evaluated)",
        created,
        capture_id,
        len(candidates),
    )

    return {
        "status": "success",
        "candidate_count": len(candidates),
        "relations_created": created,
        "capture_id": capture_id,
    }
