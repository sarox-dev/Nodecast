"""
Aggregate Creator — AI-powered grouping of related atomics into aggregate nodes.
Scans atomics with related_to relations, finds clusters, and creates
type=aggregate atomics with child_of relations.

Idempotent: skips already-aggregated atomics.
"""

import json
import logging
from collections import defaultdict

from app.services.ai_crypto import decrypt_api_key
from app.services.ai_client import call_ai_model
from app.services.database import (
    get_ai_assignment_for_feature,
    get_ai_provider,
    get_db,
    insert_atomic,
    insert_atomic_relation,
    get_atomic_relations,
)

logger = logging.getLogger(__name__)

FEATURE_AGGREGATE_CREATION = "aggregate_creation"

AGGREGATE_SYSTEM_PROMPT = """You are a knowledge base aggregation assistant. Given a list of related atomic knowledge fragments, decide if they belong together in a group.

Each fragment has: type, content, source_url

If the fragments share a common topic (e.g., all about "Docker", "Python", "API design"), output a single line:
AGGREGATE: <topic name>

If the fragments are NOT about the same topic, output:
SKIP

Output ONLY that line. No markdown, no JSON, no extra text."""


def create_aggregates_for_user(user_id: str) -> dict:
    """Scan all atomics with related_to relations and create aggregate nodes.
    Returns stats about created aggregates."""
    conn = get_db(user_id)
    try:
        # Find atomics that have related_to relations and are NOT already child_of something
        rows = conn.execute("""
            SELECT DISTINCT a.id, a.type, a.content, a.source_id
            FROM atomics a
            JOIN atomic_relations ar ON a.id = ar.source_atomic_id
            WHERE ar.relation_type = 'related_to'
              AND a.id NOT IN (
                SELECT target_atomic_id FROM atomic_relations WHERE relation_type = 'child_of'
              )
            ORDER BY a.created_at DESC
        """).fetchall()
        related_atomics = [dict(r) for r in rows]
    finally:
        conn.close()

    if not related_atomics:
        return {"status": "success", "groups_found": 0, "aggregates_created": 0}

    # Group by shared keywords
    groups = _cluster_atomics(user_id, related_atomics)
    if not groups:
        return {"status": "success", "groups_found": 0, "aggregates_created": 0}

    # For each group, ask AI to verify and name
    created = 0
    for group in groups:
        if len(group) < 2:
            continue
        name = _ai_verify_group(user_id, group)
        if not name:
            continue

        # Check if aggregate with this name already exists
        conn = get_db(user_id)
        try:
            existing = conn.execute(
                "SELECT id FROM atomics WHERE type='aggregate' AND content=?",
                (name,),
            ).fetchone()
            if existing:
                agg_id = existing["id"]
            else:
                agg_id = insert_atomic(
                    user_id, "aggregate", name,
                    properties={"source": "ai-aggregate"},
                    extracted_by="ai-aggregate",
                )
        finally:
            conn.close()

        # Link all group members as children
        for a in group:
            existing_rels = get_atomic_relations(user_id, a["id"])
            already_child = any(
                r["relation_type"] == "child_of" and r["target_atomic_id"] == agg_id
                for r in existing_rels
            )
            if not already_child:
                insert_atomic_relation(
                    user_id, agg_id, a["id"],
                    "child_of", strength=1.0,
                    context=f"Grouped under {name}",
                )
        created += 1

    return {"status": "success", "groups_found": len(groups), "aggregates_created": created}


def _cluster_atomics(user_id: str, atomics: list[dict]) -> list[list[dict]]:
    """Group atomics by shared keywords (deterministic, no AI)."""
    from app.services.atomic_relations import extract_keywords

    # Build keyword→atomics index
    kw_map: dict[str, list[dict]] = defaultdict(list)
    for a in atomics:
        content = (a.get("content") or "")
        keywords = extract_keywords(content)
        for kw in keywords:
            kw_map[kw].append(a)

    # Cluster: atomics sharing ≥2 keywords go together
    used = set()
    groups = []
    for a in atomics:
        if a["id"] in used:
            continue
        cluster = [a]
        used.add(a["id"])
        content = (a.get("content") or "")
        keywords = extract_keywords(content)
        # Find others sharing ≥2 keywords
        for kw in keywords:
            for other in kw_map.get(kw, []):
                if other["id"] not in used:
                    other_content = (other.get("content") or "")
                    other_kw = extract_keywords(other_content)
                    overlap = keywords & other_kw
                    if len(overlap) >= 2:
                        cluster.append(other)
                        used.add(other["id"])
        if len(cluster) >= 2:
            groups.append(cluster)
    return groups


def _ai_verify_group(user_id: str, group: list[dict]) -> str | None:
    """Ask AI to verify if atomics belong together and name the group.
    REQUIRES AI assignment — no fallback without AI."""
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_AGGREGATE_CREATION)
    if not assignment:
        return None

    provider = get_ai_provider(user_id, assignment["provider_id"])
    if not provider:
        return None

    # Build context
    lines = []
    for a in group[:8]:
        content = (a.get("content") or "")[:100]
        src = a.get("source_url", "") or a.get("source_id", "")[:12]
        lines.append(f"type={a['type']} | {content} | source={src}")
    context = "\n".join(lines)

    messages = [
        {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT},
        {"role": "user", "content": context[:4000]},
    ]
    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))
    result = call_ai_model(
        base_url=provider["base_url"],
        api_key=api_key,
        model=assignment["model"],
        messages=messages,
        timeout=30,
    )
    if not result:
        return None
    result = result.strip()
    if result.startswith("AGGREGATE:"):
        name = result[9:].strip().strip("\"'").strip()
        return name if name else None
    return None
