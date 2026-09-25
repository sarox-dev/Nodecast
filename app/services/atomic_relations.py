"""
Deterministic cross-source relation discovery — finds atomics from different
sources with shared keywords and creates related_to relations.

Runs as a background job. Triggers after each new atomic batch.
"""

import json
import logging
import re
from collections import Counter

from app.services.database import (
    get_db,
    insert_atomic_relation,
    get_atomic_relations,
    search_atomics,
)

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and", "or",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "can", "could", "shall", "should",
    "may", "might", "must", "this", "that", "these", "those", "it", "its",
    "you", "your", "we", "our", "they", "them", "their", "he", "she", "him",
    "his", "her", "not", "no", "nor", "but", "if", "then", "else", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "only", "own", "same", "so", "than",
    "too", "very", "just", "because", "about", "into", "over", "after",
    "before", "between", "under", "above", "below", "up", "down", "out",
    "off", "back", "through", "from", "with", "without", "within",
    "like", "via", "using", "based", "also", "well", "get", "got", "use",
    "used", "using", "make", "made", "need", "run", "running", "set",
    "setting", "work", "working", "way", "thing", "things",
    "-", "--", "–", "—",
}


def extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text. Returns set of lowercase tokens."""
    if not text:
        return set()
    text = text.lower()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_.#+-]{2,}", text)
    keywords = set()
    for t in tokens:
        t_clean = t.strip(".#-+").strip()
        if len(t_clean) < 3:
            continue
        if t_clean in STOP_WORDS:
            continue
        keywords.add(t_clean)
    return keywords


def discover_relations_for_atomic(user_id: str, atomic_id: str) -> dict:
    """
    Find atomics from DIFFERENT sources with shared keywords
    and create related_to relations. Returns stats.
    """
    conn = get_db(user_id)
    try:
        atomic = conn.execute("SELECT * FROM atomics WHERE id=?", (atomic_id,)).fetchone()
        if not atomic:
            return {"status": "skipped", "message": "Atomic not found"}
        atomic = dict(atomic)
        source_id = atomic.get("source_id", "")
        atype = atomic.get("type", "text")
        content = (atomic.get("content", "") or "")[:3000]
    finally:
        conn.close()

    keywords = extract_keywords(content)
    if not keywords:
        return {"status": "skipped", "message": "No keywords found"}

    # Query for similar atomics from different sources
    conn = get_db(user_id)
    try:
        # Build WHERE clause from keywords
        like_clauses = " OR ".join(f"a.content LIKE ?" for _ in keywords)
        query = f"""
            SELECT a.id, a.content, a.source_id, a.type, a.extracted_by, a.confidence
            FROM atomics a
            WHERE ({like_clauses})
              AND a.id != ?
              AND a.source_id != ?
              AND a.source_id IS NOT NULL
              AND a.source_id != ''
            GROUP BY a.id
            ORDER BY a.relevance DESC
            LIMIT 15
        """
        params = [f"%{kw}%" for kw in keywords] + [atomic_id, source_id]
        candidates = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    if not candidates:
        return {"status": "success", "candidates_found": 0, "relations_created": 0}

    created = 0
    for cand in candidates:
        cand_id = cand["id"]
        cand_content = (cand["content"] or "")[:3000]

        cand_keywords = extract_keywords(cand_content)
        overlap = keywords & cand_keywords
        union = keywords | cand_keywords
        if not union:
            continue
        jaccard = len(overlap) / len(union)
        if jaccard < 0.1:
            continue

        # Don't create duplicate relation
        existing = get_atomic_relations(user_id, atomic_id)
        already_related = any(
            r["target_atomic_id"] == cand_id or r["source_atomic_id"] == cand_id
            for r in existing
        )
        if already_related:
            continue

        context = f"shared: {', '.join(sorted(overlap)[:5])}"
        insert_atomic_relation(
            user_id, atomic_id, cand_id,
            "related_to", strength=round(jaccard, 3), context=context,
        )
        created += 1

    return {
        "status": "success",
        "candidates_found": len(candidates),
        "relations_created": created,
    }


def discover_relations_for_capture(user_id: str, capture_id: str) -> dict:
    """Run relation discovery for all atomics belonging to a capture."""
    conn = get_db(user_id)
    try:
        atomics = conn.execute(
            "SELECT id, type FROM atomics WHERE source_id=? AND type NOT IN ('entity', 'aggregate', 'tag')",
            (capture_id,),
        ).fetchall()
        ids = [r["id"] for r in atomics]
    finally:
        conn.close()

    total_created = 0
    for aid in ids:
        result = discover_relations_for_atomic(user_id, aid)
        total_created += result.get("relations_created", 0)

    return {"status": "success", "atomics_processed": len(ids), "total_relations_created": total_created}