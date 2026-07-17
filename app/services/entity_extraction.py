"""
Entity Extraction Service — extract normalised entities from captured content
using an OpenAI-compatible AI provider.

Feature: entity_extraction
Stores results in entities + capture_entities tables.
"""
import json
import logging
import re
from uuid import uuid4
from datetime import datetime, timezone

import httpx

from app.services.ai_crypto import decrypt_api_key
from app.services.ai_tagging import _build_context, _call_ai_model, _parse_ai_response
from app.services.database import (
    get_ai_assignment_for_feature,
    get_ai_provider,
    get_db,
    delete_capture_entities,
)

logger = logging.getLogger(__name__)

FEATURE_ENTITY_EXTRACTION = "entity_extraction"

ENTITY_TYPES = ("tool", "person", "concept", "framework", "language", "platform", "company")

ENTITY_SYSTEM_PROMPT = """You are a knowledge base entity extraction assistant. Given captured web content with priority markers, extract the key entities mentioned as plain text.

IMPORTANT RULES:
- Extract REAL entities only — specific tools, people, concepts, frameworks, languages, platforms, companies.
- Do NOT invent entities. Only extract what is explicitly mentioned or clearly referenced.
- Prefer existing entities from the list below when they match — reuse their name and type.
- Only create new entities when no existing match is found (match by name or aliases).

Output ONE line per entity in this exact format (NO markdown, NO JSON, NO extra text):
Entity: <name> | <type> | <aliases> | <description>

Where:
- type is one of: tool, person, concept, framework, language, platform, company
- aliases are comma-separated (or leave empty)
- description is one sentence (or leave empty)

Example:
Entity: Python | language | python3, CPython | A high-level programming language
Entity: FastAPI | framework | | A Python web framework

Existing entities available for reuse (match by name or aliases, reuse their name and type):
{existing_entities_list}"""


# ─── Existing entities lookup ─────────────────────────────────────


def _get_existing_entities(user_id: str) -> list[dict]:
    """Collect all existing entities from the DB."""
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            "SELECT id, name, type, aliases, description FROM entities ORDER BY capture_count DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _build_entity_system_prompt(user_id: str) -> str:
    """Build the system prompt with existing entities."""
    existing = _get_existing_entities(user_id)
    if existing:
        lines = []
        for e in existing:
            aliases = e.get("aliases", "[]")
            if isinstance(aliases, str):
                aliases = json.loads(aliases)
            alias_str = ", ".join(aliases) if aliases else ""
            if alias_str:
                lines.append(f'Entity: {e["name"]} | {e["type"]} | {alias_str} | {e.get("description", "")}')
            else:
                lines.append(f'Entity: {e["name"]} | {e["type"]} | | {e.get("description", "")}')
        entities_str = "\n".join(lines)
    else:
        entities_str = "(none yet — create new entities)"
    return ENTITY_SYSTEM_PROMPT.replace("{existing_entities_list}", entities_str)


# ─── Entity storage ──────────────────────────────────────────────


def _normalise_entity_name(name: str) -> str:
    """Normalise an entity name for matching: strip, lowercase."""
    return name.strip()


def _match_existing_entity(
    name: str, existing: list[dict]
) -> dict | None:
    """Try to match a name to existing entities (exact name or alias match)."""
    normalised = _normalise_entity_name(name)
    for e in existing:
        # Name match
        if _normalise_entity_name(e["name"]) == normalised:
            return e
        # Alias match
        aliases = e.get("aliases", "[]")
        if isinstance(aliases, str):
            aliases = json.loads(aliases)
        for alias in aliases:
            if _normalise_entity_name(alias) == normalised:
                return e
    return None


def _upsert_entity(
    user_id: str,
    name: str,
    type_: str,
    aliases: list[str],
    description: str,
) -> str:
    """Insert a new entity or update capture_count on existing match.
    Returns the entity ID."""
    conn = get_db(user_id)
    try:
        normalised = _normalise_entity_name(name)

        # Check if entity with this name already exists
        existing = conn.execute(
            "SELECT id, name, aliases, description FROM entities WHERE LOWER(name)=LOWER(?)",
            (normalised,),
        ).fetchone()

        if existing:
            entity_id = existing["id"]
            # Update capture_count
            conn.execute(
                "UPDATE entities SET capture_count = capture_count + 1 WHERE id=?",
                (entity_id,),
            )
            # Merge aliases if new ones found
            old_aliases = json.loads(existing["aliases"]) if isinstance(existing["aliases"], str) else []
            new_aliases = [a for a in aliases if a not in old_aliases]
            if new_aliases:
                merged = old_aliases + new_aliases
                conn.execute(
                    "UPDATE entities SET aliases=? WHERE id=?",
                    (json.dumps(merged), entity_id),
                )
            # Update description if current is empty
            if not existing["description"] and description:
                conn.execute(
                    "UPDATE entities SET description=? WHERE id=?",
                    (description[:500], entity_id),
                )
            conn.commit()
            return entity_id

        # Create new entity
        entity_id = uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO entities (id, name, type, aliases, description, capture_count, created_at)
               VALUES (?,?,?,?,?,1,?)""",
            (entity_id, name.strip(), type_, json.dumps(aliases), description[:500], now),
        )
        conn.commit()
        return entity_id
    finally:
        conn.close()


def _link_entity_to_capture(
    user_id: str,
    capture_id: str,
    entity_id: str,
    confidence: float = 1.0,
):
    """Link an entity to a capture in the capture_entities junction table."""
    conn = get_db(user_id)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO capture_entities (capture_id, entity_id, confidence)
               VALUES (?,?,?)""",
            (capture_id, entity_id, confidence),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Main API ────────────────────────────────────────────────────


def _parse_entities_text(text: str) -> list[dict]:
    """Parse entities from plain text format.
    Expected: Entity: <name> | <type> | <aliases> | <description>
    Also handles lines without "Entity:" prefix (just pipe-delimited).
    """
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
        # Accept "Entity:" prefix OR just straight pipe-delimited lines
        if line.upper().startswith("ENTITY"):
            # Handle "Entity:" or "Entity" variations
            after_prefix = line[6:].lstrip(": ").strip()
        else:
            after_prefix = line

        # Must have at least a name (something before the first |)
        parts = [p.strip() for p in after_prefix.split("|")]
        name = parts[0] if len(parts) > 0 else ""
        if not name:
            continue

        type_ = parts[1].lower().strip() if len(parts) > 1 else "concept"
        aliases_str = parts[2].strip() if len(parts) > 2 else ""
        aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
        description = parts[3].strip() if len(parts) > 3 else ""

        valid_types = ("tool", "person", "concept", "framework", "language", "platform", "company")
        entities.append({
            "name": name,
            "type": type_ if type_ in valid_types else "concept",
            "aliases": aliases,
            "description": description,
        })
    return entities


def extract_entities(user_id: str, capture_id: str) -> dict:
    """Extract entities from a capture using the configured AI provider.

    Returns dict with status: 'success', 'skipped', 'error', 'no_assignment'.
    """
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_ENTITY_EXTRACTION)
    if not assignment:
        return {
            "status": "no_assignment",
            "message": "No AI provider assigned for entity extraction. Go to Settings → AI to configure.",
        }

    provider = get_ai_provider(user_id, assignment["provider_id"])
    if not provider:
        return {"status": "error", "message": "AI provider not found"}

    # Build context (reuse ai_tagging's context builder)
    context, site_name = _build_context(user_id, capture_id)
    if not context:
        return {"status": "skipped", "message": "No content to analyze"}

    # Build dynamic system prompt with existing entities
    system_prompt = _build_entity_system_prompt(user_id)

    # Decrypt API key
    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))

    # Call AI
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]
    result = _call_ai_model(
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

    # Delete old entity links for this capture before inserting new ones
    delete_capture_entities(user_id, capture_id)

    # Get existing entities for matching
    existing = _get_existing_entities(user_id)

    linked = 0
    entities_out = []
    for raw in raw_entities:
        name = raw.get("name", "").strip()
        if not name:
            continue
        type_ = raw.get("type", "concept")
        if type_ not in ENTITY_TYPES:
            type_ = "concept"
        aliases = raw.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases] if aliases.strip() else []
        description = raw.get("description", "")

        # Match existing or create new
        match = _match_existing_entity(name, existing)
        if match:
            entity_id = match["id"]
            # Still update capture_count
            conn = get_db(user_id)
            try:
                conn.execute(
                    "UPDATE entities SET capture_count = capture_count + 1 WHERE id=?",
                    (entity_id,),
                )
                conn.commit()
            finally:
                conn.close()
        else:
            entity_id = _upsert_entity(user_id, name, type_, aliases, description)
            # Add to existing list for subsequent matching in same batch
            existing.append({
                "id": entity_id,
                "name": name,
                "type": type_,
                "aliases": json.dumps(aliases),
                "description": description,
            })

        # Link to capture
        _link_entity_to_capture(user_id, capture_id, entity_id, 1.0)
        linked += 1
        entities_out.append({
            "id": entity_id,
            "name": name,
            "type": type_,
        })

    return {"status": "success", "data": {"entities": entities_out, "linked": linked}}