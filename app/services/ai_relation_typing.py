"""
AI Relation Typing Service — Stage 2: uses AI to classify capture↔capture
relations into specific types (depends_on, references, supports, etc.).

Called AFTER Stage 1 (Jaccard) has created `related` candidates.
Stage 2 re-types each candidate by analyzing capture content.
"""

import json
import logging

import httpx

from app.services.ai_crypto import decrypt_api_key
from app.services.database import (
    get_db,
    get_ai_provider,
    get_ai_assignment_for_feature,
    get_capture_ai_tags,
    get_relations_for_capture,
    update_relation_type,
    delete_relation_by_id,
    add_rejected_relation,
    RELATION_TYPES,
)

logger = logging.getLogger(__name__)

FEATURE_RELATION_TYPING = "relation_typing"

RELATION_TYPES_LIST = ", ".join(t for t in RELATION_TYPES if t not in ("related",))

RELATION_TYPING_PROMPT = f"""You are a knowledge graph relationship classifier. Given two connected captures (SOURCE and TARGET) from a personal knowledge base, classify the relationship or decide they are NOT related.

If the two captures are genuinely related, choose ONE of these types:
{RELATION_TYPES_LIST}

Definitions:
- related_to: Generic connection, no stronger type fits
- depends_on: SOURCE requires TARGET to function or exist
- implements: SOURCE is a concrete implementation of TARGET (a concept/standard)
- references: SOURCE cites, quotes, or mentions TARGET
- supports: SOURCE provides evidence or backing for TARGET
- contradicts: SOURCE opposes or conflicts with TARGET
- part_of: SOURCE is a component, chapter, or section of TARGET
- similar_to: SOURCE and TARGET are conceptually similar but neither depends on the other
- version_of: SOURCE is a newer version, iteration, or alternative of TARGET

If the two captures are NOT meaningfully related (e.g. they only share a common entity/person/tool but are about different topics), output:
relation_type: none
reasoning: Briefly explain why they are not related

Output format (plain text, no markdown):
relation_type: <type or "none">
reasoning: <one short sentence explaining why>
confidence: <0.0-1.0>

Examples:
relation_type: references
reasoning: SOURCE article cites the research paper in TARGET as a primary source
confidence: 0.92

relation_type: none
reasoning: Both mention OpenRouter but SOURCE is about AI coding tools while TARGET is about blog writing
confidence: 0.85"""


def _get_capture_summary(user_id: str, capture_id: str) -> str:
    tags = get_capture_ai_tags(user_id, capture_id)
    if tags and tags.get("summary"):
        return tags["summary"]
    return ""


def _get_capture_tags_flat(user_id: str, capture_id: str) -> str:
    tags = get_capture_ai_tags(user_id, capture_id)
    if tags and tags.get("tags"):
        raw = tags["tags"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(raw, list) and raw:
            return ", ".join(str(t) for t in raw[:8])
    return ""


def _get_capture_entities_text(user_id: str, capture_id: str) -> str:
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            """SELECT e.name FROM entities e
               JOIN capture_entities ce ON e.id = ce.entity_id
               WHERE ce.capture_id=?""",
            (capture_id,),
        ).fetchall()
        names = [r["name"] for r in rows if r["name"]]
        return ", ".join(names[:8])
    finally:
        conn.close()


def _get_capture_title(user_id: str, capture_id: str) -> str:
    conn = get_db(user_id)
    try:
        row = conn.execute(
            "SELECT source_title FROM captures WHERE id=?", (capture_id,)
        ).fetchone()
        return row["source_title"] or "" if row else ""
    finally:
        conn.close()


def _build_pair_context(
    user_id: str, source_id: str, target_id: str
) -> str | None:
    src_title = _get_capture_title(user_id, source_id)
    tgt_title = _get_capture_title(user_id, target_id)
    if not src_title and not tgt_title:
        return None

    src_summary = _get_capture_summary(user_id, source_id)
    tgt_summary = _get_capture_summary(user_id, target_id)
    src_tags = _get_capture_tags_flat(user_id, source_id)
    tgt_tags = _get_capture_tags_flat(user_id, target_id)
    src_entities = _get_capture_entities_text(user_id, source_id)
    tgt_entities = _get_capture_entities_text(user_id, target_id)

    parts = []

    src_label = src_title[:80] or source_id[:12]
    tgt_label = tgt_title[:80] or target_id[:12]

    parts.append(f'SOURCE: "{src_label}"')
    if src_summary:
        parts.append(f"  Summary: {src_summary[:200]}")
    if src_tags:
        parts.append(f"  Tags: {src_tags}")
    if src_entities:
        parts.append(f"  Entities: {src_entities}")

    parts.append(f'TARGET: "{tgt_label}"')
    if tgt_summary:
        parts.append(f"  Summary: {tgt_summary[:200]}")
    if tgt_tags:
        parts.append(f"  Tags: {tgt_tags}")
    if tgt_entities:
        parts.append(f"  Entities: {tgt_entities}")

    return "\n".join(parts)


def _call_ai_typing(
    base_url: str, api_key: str, model: str, context: str
) -> dict | None:
    messages = [
        {"role": "system", "content": RELATION_TYPING_PROMPT},
        {"role": "user", "content": context},
    ]
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 200,
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            if not content.strip():
                reasoning = data["choices"][0]["message"].get("reasoning_content", "")
                if reasoning.strip():
                    content = reasoning
            if not content.strip():
                return None
            return _parse_typing_response(content)
    except httpx.ConnectError:
        logger.error("AI relation typing: Connection refused to %s", base_url)
        return None
    except httpx.TimeoutException:
        logger.error("AI relation typing: Timeout at %s", base_url)
        return None
    except Exception as exc:
        logger.error("AI relation typing error: %s", exc)
        return None


def _parse_typing_response(text: str) -> dict | None:
    rtype = ""
    reasoning = ""
    confidence = 0.5

    for line in text.strip().split("\n"):
        line = line.strip()
        lower = line.lower()
        if lower.startswith("relation_type:"):
            rtype = line.split(":", 1)[1].strip().lower().rstrip(".,;")
        elif lower.startswith("reasoning:"):
            reasoning = line.split(":", 1)[1].strip()
        elif lower.startswith("confidence:"):
            try:
                confidence = float(line.split(":", 1)[1].strip().rstrip(".,;"))
            except (ValueError, IndexError):
                pass

    if rtype == "none":
        return {
            "relation_type": "none",
            "reasoning": reasoning[:200],
            "confidence": max(0.0, min(1.0, confidence)),
        }

    if rtype not in RELATION_TYPES:
        logger.warning(
            "AI returned invalid relation type '%s' — treating as none",
            rtype,
        )
        return {
            "relation_type": "none",
            "reasoning": f"AI returned invalid type: {rtype}",
            "confidence": 0.5,
        }

    if rtype == "related_to":
        return None

    confidence = max(0.0, min(1.0, confidence))

    return {
        "relation_type": rtype,
        "reasoning": reasoning[:200],
        "confidence": confidence,
    }


def type_relation_pair(
    user_id: str, source_id: str, target_id: str, relation_id: str = ""
) -> dict:
    context = _build_pair_context(user_id, source_id, target_id)
    if not context:
        return {"status": "skipped", "message": "No content for both captures"}

    assignment = get_ai_assignment_for_feature(user_id, FEATURE_RELATION_TYPING)
    if not assignment:
        return {
            "status": "no_assignment",
            "message": "No AI provider assigned for relation typing",
        }

    provider = get_ai_provider(user_id, assignment["provider_id"])
    if not provider:
        return {"status": "error", "message": "AI provider not found"}

    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))
    result = _call_ai_typing(
        base_url=provider["base_url"],
        api_key=api_key,
        model=assignment["model"],
        context=context,
    )

    if not result:
        return {"status": "skipped", "message": "AI returned related_to or no valid type"}

    if result["relation_type"] == "none":
        if relation_id:
            delete_relation_by_id(user_id, relation_id)
            add_rejected_relation(user_id, source_id, target_id)
            logger.info(
                "Rejected relation %s: not related (confidence=%.2f)",
                relation_id,
                result["confidence"],
            )
        return {
            "status": "success",
            "relation_type": "none",
            "reasoning": result["reasoning"],
            "confidence": result["confidence"],
        }

    if relation_id:
        update_relation_type(
            user_id=user_id,
            relation_id=relation_id,
            new_type=result["relation_type"],
            context=result["reasoning"],
        )
        logger.info(
            "Typed relation %s: %s (confidence=%.2f)",
            relation_id,
            result["relation_type"],
            result["confidence"],
        )

    return {
        "status": "success",
        "relation_type": result["relation_type"],
        "reasoning": result["reasoning"],
        "confidence": result["confidence"],
    }


def type_relations_for_capture(user_id: str, capture_id: str) -> dict:
    relations = get_relations_for_capture(user_id, capture_id)
    related_relations = [
        r for r in relations
        if r["relation_type"] in ("related", "related_to")
        and r["source_type"] == "capture"
        and r["target_type"] == "capture"
    ]

    if not related_relations:
        return {"status": "success", "total": 0, "typed": 0, "skipped": 0}

    total = len(related_relations)
    typed = 0
    skipped = 0

    for rel in related_relations:
        rid = rel["id"]
        source_id = rel["source_id"]
        target_id = rel["target_id"]

        result = type_relation_pair(
            user_id=user_id,
            source_id=source_id,
            target_id=target_id,
            relation_id=rid,
        )

        if result.get("status") == "success":
            typed += 1
            # Bidirectional: also update reverse relation if it exists
            if result.get("relation_type") not in ("none",):
                conn = get_db(user_id)
                try:
                    reverse = conn.execute(
                        """SELECT id FROM relations
                           WHERE source_type='capture' AND source_id=?
                             AND target_type='capture' AND target_id=?
                             AND relation_type IN ('related', 'related_to')""",
                        (target_id, source_id),
                    ).fetchone()
                    if reverse:
                        update_relation_type(
                            user_id=user_id,
                            relation_id=reverse["id"],
                            new_type=result["relation_type"],
                            context=result.get("reasoning", ""),
                        )
                        typed += 1
                finally:
                    conn.close()
        else:
            skipped += 1

    logger.info(
        "Relation typing for %s: %d/%d typed, %d skipped",
        capture_id,
        typed,
        total,
        skipped,
    )

    return {
        "status": "success",
        "total": total,
        "typed": typed,
        "skipped": skipped,
    }