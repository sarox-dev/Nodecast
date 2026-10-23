"""Rebuildable multilingual topic projections over source-bound evidence."""

from __future__ import annotations

import json
import time

from app.services.database import enrich_atomics_with_sources, get_db, insert_atomic, insert_atomic_relation
from app.services.memory_retrieval import _candidate_search


TOPIC_VERSION = "1"


def refresh_topic_view(user_id: str, title: str, queries: list[str], force: bool = False,
                       embedding_identity: tuple[str, str] | None = None) -> dict:
    canonical = title.strip().casefold()[:200]
    if not canonical:
        raise ValueError("Topic title is required")
    conn = get_db(user_id)
    try:
        row = conn.execute("SELECT * FROM atomics WHERE role='aggregate' AND canonical_key=?", (f"topic:{canonical}",)).fetchone()
    finally:
        conn.close()
    now = int(time.time())
    if row:
        props = json.loads(row["properties"] or "{}")
        if not force and now - int(props.get("rebuilt_at_epoch", 0)) < 30:
            return get_topic_view(user_id, row["id"])
        topic_id = row["id"]
    else:
        topic_id = insert_atomic(user_id, "topic", title.strip(), role="aggregate", canonical_key=f"topic:{canonical}",
                                 properties={"projection": "topic", "version": TOPIC_VERSION}, extracted_by="deterministic-topic-view")
    candidates = {}
    capabilities = []
    for query in [item.strip() for item in queries[:8] if item.strip()]:
        rows, capability = _candidate_search(user_id, query, 12, embedding_identity)
        capabilities.append(capability)
        for rank, row in enumerate(rows):
            if row.get("role", "evidence") == "evidence" and row.get("source_id"):
                candidates.setdefault(row["id"], (row, rank))
    ordered = sorted(candidates.values(), key=lambda item: (item[1], item[0]["id"]))[:24]
    conn = get_db(user_id)
    try:
        conn.execute("DELETE FROM atomic_relations WHERE source_atomic_id=? AND relation_type='topic_member' AND status='candidate'", (topic_id,))
        props = {"projection": "topic", "version": TOPIC_VERSION, "queries": queries[:8],
                 "rebuilt_at_epoch": now, "membership": "rebuildable_candidate"}
        conn.execute("UPDATE atomics SET properties=?,updated_at=datetime('now') WHERE id=?", (json.dumps(props, ensure_ascii=False), topic_id))
        conn.commit()
    finally:
        conn.close()
    for row, rank in ordered:
        insert_atomic_relation(user_id, topic_id, row["id"], "topic_member", max(.1, 1 - rank / 20),
                               method="retrieval", reason="Rebuildable topic candidate", confidence=max(.1, 1 - rank / 20), status="candidate")
    result = get_topic_view(user_id, topic_id)
    result["retrieval_capabilities"] = capabilities
    return result


def get_topic_view(user_id: str, topic_id: str) -> dict:
    conn = get_db(user_id)
    try:
        topic = conn.execute("SELECT * FROM atomics WHERE id=? AND role='aggregate'", (topic_id,)).fetchone()
        if not topic:
            raise ValueError("Topic not found")
        rows = [dict(row) for row in conn.execute("""SELECT a.* FROM atomic_relations r JOIN atomics a ON a.id=r.target_atomic_id
          WHERE r.source_atomic_id=? AND r.relation_type='topic_member' AND r.status='candidate'
            AND a.role='evidence' AND a.source_id IS NOT NULL AND a.status!='rejected'
          ORDER BY r.confidence DESC,a.position LIMIT 24""", (topic_id,))]
    finally:
        conn.close()
    evidence = enrich_atomics_with_sources(user_id, rows)
    languages = sorted({(json.loads(row.get("properties") or "{}") if isinstance(row.get("properties"), str) else row.get("properties") or {}).get("language", "und") for row in evidence})
    return {"topic_id": topic_id, "title": topic["content"], "languages": languages,
            "summary": {"kind": "deterministic", "text": f"{len(evidence)} source-bound evidence items across {len({row['source_id'] for row in evidence})} sources."},
            "evidence": evidence, "membership_status": "candidate", "version": TOPIC_VERSION}
