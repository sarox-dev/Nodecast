"""
Atomic Extraction Service — takes cleaned text, uses AI to extract atomics.
Saves atomics + creates mandatory source relations.
"""

import json
import logging

from app.services.ai_crypto import decrypt_api_key
from app.services.database import (
    get_ai_assignment_for_feature,
    get_ai_provider,
    insert_atomics_batch,
    insert_atomic_relation,
    insert_capture_ref,
    get_capture_ref,
)
from app.services.html_cleaner import extract_main_content
from app.services.ai_client import call_ai_model
from app.services.entity_extraction import extract_entities
from app.services.atomic_relations import discover_relations_for_capture
from app.services.aggregate_creator import create_aggregates_for_user

logger = logging.getLogger(__name__)

FEATURE_ATOMIC_EXTRACTION = "atomic_extraction"

ATOMIC_SYSTEM_PROMPT = """You are a knowledge atomization assistant. Given cleaned web content, extract the most important information as atomic knowledge fragments.

Each atomic fragment must be:
- The smallest logical piece of information that can stand alone
- Self-contained (understandable without context)
- One of these types:
  - "heading" — section titles (h1-h6)
  - "text" — important paragraphs, key facts, instructions
  - "code_block" — code snippets with "language" in properties
  - "quote" — notable quotes/citations
  - "link" — important reference links with "url" in properties
  - "image" — notable images with "src" and "alt" in properties
  - "entity" — specific named tools, people, companies, concepts

RULES:
- Split the content into MULTIPLE atomics — one per logical piece.
- Include position (0, 1, 2, ...) preserving original order.
- For code blocks, add properties.language (e.g. "bash", "python").
- For images, add properties.src and properties.alt.
- For links, add properties.url.
- Skip boilerplate, navigation, ads, and generic filler.
- Output at most 25 atomics.

Output ONLY a JSON array. NO markdown fences, NO extra text, NO comments.
Example:
[
  {"type": "heading", "content": "Docker Quickstart", "position": 0},
  {"type": "text", "content": "Docker is a container runtime for applications.", "position": 1},
  {"type": "code_block", "content": "docker pull ubuntu", "properties": {"language": "bash"}, "position": 2},
  {"type": "entity", "content": "Docker", "properties": {"type": "tool"}, "position": 3}
]"""


def extract_atomics_from_text(user_id: str, capture_id: str, cleaned_text: str) -> list[dict]:
    """
    Extract atomics from cleaned text using AI. Creates atomics + source relations.
    If no AI configured, creates a single 'text' atomic with the full cleaned text.
    Returns list of created atomics.
    """
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_ATOMIC_EXTRACTION)
    if assignment:
        provider = get_ai_provider(user_id, assignment["provider_id"])
        if provider:
            api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))
            messages = [
                {"role": "system", "content": ATOMIC_SYSTEM_PROMPT},
                {"role": "user", "content": cleaned_text[:8000]},
            ]
            result = call_ai_model(
                base_url=provider["base_url"],
                api_key=api_key,
                model=assignment["model"],
                messages=messages,
                timeout=60,
            )
            if result:
                parsed = _parse_atomics_json(result)
                if parsed:
                    normalized = _normalize_atomics(parsed)
                    for a in normalized:
                        a["source_id"] = capture_id
                        a["extracted_by"] = "ai-atomic-extraction"
                    ids = insert_atomics_batch(user_id, normalized)
                    for i, aid in enumerate(ids):
                        if i > 0:
                            insert_atomic_relation(
                                user_id, ids[i-1], aid, "precedes",
                                strength=1.0,
                            )
                    logger.info("Extracted %d atomics from capture %s", len(ids), capture_id[:8])
                    for i, a in enumerate(normalized):
                        a["id"] = ids[i]
                    return normalized

    # Fallback: no AI or AI failed — create single text atomic
    aid = insert_atomics_batch(user_id, [{
        "type": "text",
        "content": cleaned_text[:10000],
        "source_id": capture_id,
        "extracted_by": "fallback",
        "position": 0,
    }])
    if aid:
        return [{"id": aid[0], "type": "text", "content": cleaned_text[:10000], "source_id": capture_id}]
    return []


def _normalize_atomics(parsed: list) -> list[dict]:
    """Normalize AI output: coerce types, strip bad content, ensure position."""
    VALID_TYPES = {"heading", "text", "fact", "summary", "tag", "code_block", "quote", "link", "image", "entity"}
    result = []
    position = 0
    for item in parsed:
        if not isinstance(item, dict):
            continue
        atype = str(item.get("type", "text")).strip().lower()
        if atype not in VALID_TYPES:
            atype = "text"
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        props = item.get("properties")
        if not isinstance(props, dict):
            props = {}
        # For entity atomics, hoist properties.type into a proper field
        if atype == "entity" and not props.get("entity_type"):
            ent_type = str(item.get("entity_type", "") or props.get("type", "")).strip()
            if ent_type:
                props["entity_type"] = ent_type
            elif "type" in props and props["type"] not in ("tool", "person", "concept", "framework", "language", "platform", "company"):
                props["entity_type"] = str(props["type"])
        result.append({
            "type": atype,
            "content": content[:2000],
            "properties": props,
            "position": position,
        })
        position += 1
    return result


def _parse_atomics_json(text: str) -> list[dict] | None:
    """Parse JSON array from AI response. Handles markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return None
    except json.JSONDecodeError:
        return None


def process_capture_to_atomics(user_id: str, capture_id: str, page_html: str | None, capture_ref: dict) -> dict:
    """
    Full pipeline for a capture with highlighted text:
    1. Clean HTML
    2. Extract atomics via AI
    3. Return atomics
    
    For captures without highlighted text (bookmarks): no atomics created.
    """
    anchor = capture_ref.get("anchor") or {}
    anchor_text = str(anchor.get("selected_text") or "").strip() if isinstance(anchor, dict) else ""
    if not page_html and not anchor_text:
        return {"atomics": [], "message": "No highlighted content to process"}

    cleaned = anchor_text or extract_main_content(page_html or "")
    if not cleaned.strip():
        return {"atomics": [], "message": "No clean content extracted"}

    atomics = extract_atomics_from_text(user_id, capture_id, cleaned)

    # Include the user's highlighted selection as its own atomic if present
    if anchor_text and not any(
        a.get("content", "").strip() == anchor_text for a in atomics
    ):
        aid = insert_atomics_batch(user_id, [{
            "type": "text",
            "content": anchor_text[:2000],
            "source_id": capture_id,
            "extracted_by": "user-selection",
            "position": -1,
        }])
        if aid:
            atomics.insert(0, {"id": aid[0], "type": "text", "content": anchor_text[:2000], "source_id": capture_id})

    # Auto-trigger entity extraction if atomics were created
    if atomics:
        try:
            extract_entities(user_id, capture_id)
        except Exception:
            logger.exception("Entity extraction failed for capture %s", capture_id[:8])

    # Auto-trigger cross-source relation discovery
    if atomics:
        try:
            discover_relations_for_capture(user_id, capture_id)
        except Exception:
            logger.exception("Relation discovery failed for capture %s", capture_id[:8])

    # Auto-trigger aggregate creation
    try:
        create_aggregates_for_user(user_id)
    except Exception:
        logger.exception("Aggregate creation failed for user %s", user_id[:8])

    return {
        "atomics": atomics,
        "cleaned_length": len(cleaned),
        "atomic_count": len(atomics),
    }


def extract_atomics_for_capture(user_id: str, capture_id: str) -> dict:
    """
    Batch-friendly entry point: loads raw HTML for a capture and runs atomic extraction.
    Returns dict with status + atomics (or error/skipped).
    """
    from app.services.raw_storage import get_raw_html, load_raw_capture
    from app.services.database import get_capture_ref

    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        return {"status": "skipped", "message": "Capture not found"}

    html = get_raw_html(user_id, capture_id)
    if not html:
        return {"status": "skipped", "message": "No HTML available"}

    raw = load_raw_capture(user_id, capture_id)
    anchor = raw.anchor.model_dump() if raw and raw.anchor else None
    if not anchor or not anchor.get("selected_text"):
        return {"status": "skipped", "message": "Bookmark has no highlighted content"}
    result = process_capture_to_atomics(user_id, capture_id, html, {"anchor": anchor})
    count = result.get("atomic_count", 0)
    return {
        "status": "success" if count else "skipped",
        "atomic_count": count,
        "data": {"count": count, "atomics": result.get("atomics", [])},
        "message": f"Extracted {count} atomics",
    }
