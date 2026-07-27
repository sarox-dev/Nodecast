"""
Relation Discovery Service — Stage 1: deterministic candidate matching
based on shared tags and entities (0 AI tokens).

Uses Jaccard similarity to find related captures and creates `related_to`
relations with strength = combined_score. Also discovers entity↔entity
connections via shared captures.

After Stage 1, runs Stage 2 (AI connection typing) if the user has
a provider configured for relation_typing.
"""

import json
import logging

from app.services.database import (
    get_db,
    insert_relation,
    delete_relations_for_capture,
    RELATION_TYPES,
    get_ai_assignment_for_feature,
    is_relation_rejected,
)

logger = logging.getLogger(__name__)

FEATURE_RELATION_DISCOVERY = "relation_discovery"
FEATURE_RELATION_TYPING = "relation_typing"

# ─── Scoring constants ──────────────────────────────────────────────

TAG_WEIGHT = 0.3
ENTITY_WEIGHT = 0.7
MAX_CANDIDATES = 25
MIN_STRENGTH = 0.05

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
        if is_relation_rejected(user_id, capture_id, cid):
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
                relation_type="related",
                strength=strength,
                context=context,
            )
            created += 1

    return created


# ─── Main discover function ─────────────────────────────────────────


def discover_relations_stage1(user_id: str, capture_id: str) -> dict:
    """Stage 1 only: Jaccard-based candidate discovery, NO AI typing.
    Preserves existing typed relations (non-related) — only replaces `related` ones.
    Skips pairs that were previously rejected by AI."""
    conn = get_db(user_id)
    try:
        existing_typed = {
            r["target_id"]: {
                "relation_type": r["relation_type"],
                "target_type": r["target_type"],
                "context": "",
                "strength": 0.5,
            }
            for r in conn.execute(
                """SELECT target_type, target_id, relation_type, context, strength FROM relations
                   WHERE (source_type='capture' AND source_id=?)
                     AND relation_type NOT IN ('related', 'related_to')""",
                (capture_id,),
            ).fetchall()
        }
    finally:
        conn.close()

    delete_relations_for_capture(user_id, capture_id)

    if existing_typed:
        conn2 = get_db(user_id)
        try:
            for tid, info in existing_typed.items():
                insert_relation(
                    user_id=user_id,
                    source_type="capture",
                    source_id=capture_id,
                    target_type=info["target_type"],
                    target_id=tid,
                    relation_type=info["relation_type"],
                    strength=info["strength"],
                    context=info["context"],
                )
        finally:
            conn2.close()

    candidates = find_relation_candidates(user_id, capture_id)
    if not candidates:
        logger.info("No candidates found for capture %s", capture_id)
        return {"status": "success", "candidate_count": 0, "relations_created": 0}

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
        if cid in existing_typed:
            continue
        if is_relation_rejected(user_id, capture_id, cid):
            continue
        context_parts = []
        if shared_tags:
            context_parts.append(f"shared tags: {', '.join(sorted(shared_tags)[:5])}")
        if shared_entities:
            context_parts.append(f"shared entities: {', '.join(sorted(shared_entities)[:5])}")

        other_title = title_map.get(cid, "")
        context = f"Related to \"{other_title}\". " if other_title else ""
        context += "; ".join(context_parts)

        insert_relation(
            user_id=user_id,
            source_type="capture",
            source_id=capture_id,
            target_type="capture",
            target_id=cid,
            relation_type="related",
            strength=round(score, 4),
            context=context,
        )
        created += 1

    logger.info(
        "Stage 1: %d new relations for capture %s (%d typed preserved)",
        created,
        capture_id,
        len(existing_typed),
    )

    return {
        "status": "success",
        "candidate_count": len(candidates),
        "relations_created": created,
        "typed_preserved": len(existing_typed),
        "capture_id": capture_id,
    }


def discover_relations(user_id: str, capture_id: str) -> dict:
    """Run Stage 1 + auto-trigger Stage 2 AI typing if configured."""
    result = discover_relations_stage1(user_id, capture_id)
    created = result.get("relations_created", 0)

    if created > 0:
        try:
            assignment = get_ai_assignment_for_feature(user_id, FEATURE_RELATION_TYPING)
            if assignment:
                from app.services.ai_relation_typing import type_relations_for_capture
                typing_result = type_relations_for_capture(user_id, capture_id)
                typed_count = typing_result.get("typed", 0)
                result["relations_typed"] = typed_count
                logger.info(
                    "Stage 2: %d/%d relations typed for %s",
                    typed_count, created, capture_id,
                )
        except Exception as exc:
            logger.warning("Stage 2 typing failed for %s: %s", capture_id, exc)

    return result
