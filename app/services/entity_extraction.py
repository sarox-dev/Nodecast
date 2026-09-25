"""
Entity Extraction Service — extract entities as atomics using AI.
Stores results as atomic(type=entity) with relations to source atomics.
"""

import json
import logging

from app.services.ai_crypto import decrypt_api_key
from app.services.ai_client import call_ai_model
from app.services.database import (
    get_ai_assignment_for_feature,
    get_ai_provider,
    get_db,
    insert_atomic,
    insert_atomic_relation,
    get_atomics_by_source,
    search_atomics,
)

logger = logging.getLogger(__name__)

FEATURE_ENTITY_EXTRACTION = "entity_extraction"

ENTITY_TYPES = ("tool", "person", "concept", "framework", "language", "platform", "company")

ENTITY_SYSTEM_PROMPT = """You are a knowledge base entity extraction assistant. Given captured web content, extract key entities.

IMPORTANT RULES:
- Extract REAL entities only — specific tools, people, concepts, frameworks, languages, platforms, companies.
- Do NOT invent entities. Only extract what is explicitly mentioned.
- Prefer existing entities from the list below — reuse their name and type.

Output ONE line per entity (NO markdown, NO JSON, NO extra text):
Entity: <name> | <type> | <aliases> | <description>

Types: tool, person, concept, framework, language, platform, company

Existing entities:
{existing_entities_list}"""


def _get_existing_entity_atomics(user_id: str) -> list[dict]:
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            "SELECT id, content, properties FROM atomics WHERE type='entity' ORDER BY relevance DESC"
        ).fetchall()
        result = []
        for r in rows:
            props = {}
            if isinstance(r["properties"], str):
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
            })
        return result
    finally:
        conn.close()


def _build_context_from_atomics(user_id: str, capture_id: str) -> str | None:
    """Build context from atomics for a capture (instead of knowledge_objects)."""
    atomics = get_atomics_by_source(user_id, capture_id)
    if not atomics:
        return None
    content_parts = []
    for a in atomics:
        if a["type"] in ("entity", "aggregate", "tag"):
            continue
        c = a.get("content", "").strip()
        if c:
            content_parts.append(c)
            if len("\n".join(content_parts)) > 6000:
                break
    return "\n".join(content_parts) if content_parts else None


def _build_entity_system_prompt(user_id: str) -> str:
    existing = _get_existing_entity_atomics(user_id)
    if existing:
        lines = []
        for e in existing:
            aliases = e.get("aliases", [])
            alias_str = ", ".join(aliases) if aliases else ""
            lines.append(f'Entity: {e["name"]} | {e["type"]} | {alias_str} | {e.get("description", "")}')
        entities_str = "\n".join(lines)
    else:
        entities_str = "(none yet — create new entities)"
    return ENTITY_SYSTEM_PROMPT.replace("{existing_entities_list}", entities_str)


def _match_existing_entity(name: str, existing: list[dict]) -> dict | None:
    normalized = name.strip().lower()
    for e in existing:
        if e["name"].strip().lower() == normalized:
            return e
        for alias in e.get("aliases", []):
            if alias.strip().lower() == normalized:
                return e
    return None


def _parse_entities_text(text: str) -> list[dict]:
    if not text:
        return []
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    entities = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("ENTITY"):
            after_prefix = line[6:].lstrip(": ").strip()
        else:
            after_prefix = line
        parts = [p.strip() for p in after_prefix.split("|")]
        name = parts[0] if len(parts) > 0 else ""
        if not name:
            continue
        type_ = parts[1].lower().strip() if len(parts) > 1 else "concept"
        aliases_str = parts[2].strip() if len(parts) > 2 else ""
        aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
        description = parts[3].strip() if len(parts) > 3 else ""
        if type_ not in ENTITY_TYPES:
            type_ = "concept"
        entities.append({"name": name, "type": type_, "aliases": aliases, "description": description})
    return entities


def extract_entities(user_id: str, capture_id: str) -> dict:
    """Extract entities from a capture using AI. Stores as atomic(type=entity) with relations."""
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_ENTITY_EXTRACTION)
    if not assignment:
        return {"status": "no_assignment", "message": "No AI provider assigned for entity extraction."}

    provider = get_ai_provider(user_id, assignment["provider_id"])
    if not provider:
        return {"status": "error", "message": "AI provider not found"}

    context = _build_context_from_atomics(user_id, capture_id)
    if not context:
        return {"status": "skipped", "message": "No content to analyze"}

    system_prompt = _build_entity_system_prompt(user_id)
    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context[:6000]},
    ]
    result = call_ai_model(
        base_url=provider["base_url"],
        api_key=api_key,
        model=assignment["model"],
        messages=messages,
    )

    if not result:
        return {"status": "error", "message": "AI model returned no valid response"}

    raw_entities = _parse_entities_text(result)
    if not raw_entities:
        return {"status": "success", "data": {"entities": [], "linked": 0}}

    # Get existing entity atomics for dedup
    existing = _get_existing_entity_atomics(user_id)

    linked = 0
    entities_out = []
    for raw in raw_entities:
        name = raw.get("name", "").strip()
        if not name:
            continue
        type_ = raw.get("type", "concept")
        aliases = raw.get("aliases", [])
        description = raw.get("description", "")

        # Check if entity atomic already exists
        match = _match_existing_entity(name, existing)
        if match:
            entity_id = match["id"]
        else:
            # Create new entity atomic
            props = {"entity_type": type_, "aliases": aliases, "description": description}
            entity_id = insert_atomic(
                user_id=user_id,
                atomic_type="entity",
                content=name,
                properties=props,
                source_id=capture_id,
                extracted_by="ai-entity-extraction",
            )
            existing.append({
                "id": entity_id,
                "name": name,
                "type": type_,
                "aliases": aliases,
                "description": description,
            })

        # Link entity to source atomics via relations
        source_atomics = get_atomics_by_source(user_id, capture_id)
        for sa in source_atomics:
            if sa["type"] != "entity":
                insert_atomic_relation(
                    user_id, entity_id, sa["id"], "references",
                    context=f"Entity {name} referenced in {sa.get('type', 'text')}",
                )

        linked += 1
        entities_out.append({"id": entity_id, "name": name, "type": type_})

    return {"status": "success", "data": {"entities": entities_out, "linked": linked}}
