"""
Atomic Extraction Service — takes cleaned text, uses AI to extract atomics.
Saves atomics + creates mandatory source relations.
"""

import json
import logging
import re
from datetime import datetime, timezone

from app.services.ai_crypto import decrypt_api_key
from app.services.database import (
    get_ai_assignment_for_feature,
    get_ai_provider,
    insert_atomics_batch,
    insert_atomic_relation,
    insert_capture_ref,
    get_capture_ref,
    get_db,
    insert_atomic,
)
from app.services.html_cleaner import extract_main_content
from app.services.ai_client import call_ai_model
from app.services.atomic_relations import discover_relations_for_capture
from app.services.aggregate_creator import create_aggregates_for_user

logger = logging.getLogger(__name__)

FEATURE_ATOMIC_EXTRACTION = "atomic_extraction"

ATOMIC_SYSTEM_PROMPT = """You enrich exact evidence fragments without rewriting them.

For each numbered fragment return its position, evidence type, short summary, and explicitly named concepts.
Allowed types: claim, definition, procedure_step, problem, solution, outcome, warning, measurement, code_block, quote, text.
Never paraphrase or return replacement evidence content.
Output ONLY a JSON array like:
[{"position":0,"type":"definition","summary":"Docker is described as a container runtime.","concepts":["Docker"]}]"""


def split_evidence(text: str, source_title: str = "") -> list[dict]:
    """Deterministically preserve source text as small, ordered evidence blocks."""
    blocks = []
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n|(?<!\d\.)(?<=\.)\s+(?=[A-Z0-9])", text) if chunk.strip()]
    if len(chunks) == 1:
        chunks = [line.strip() for line in text.splitlines() if line.strip()]
    for chunk in chunks[:50]:
        lower = chunk.lower()
        if re.search(r"(^|\n)(error|exception|traceback|failed)\b", lower) or re.search(r"\b[A-Z][A-Za-z]+Error\b", chunk):
            kind = "problem"
        elif re.match(r"^(step\s+\d+|\d+[.)]|[-*])\s*", lower):
            kind = "procedure_step"
        elif any(word in lower for word in ("solution", "fix", "resolve", "workaround")):
            kind = "solution"
        elif any(word in lower for word in ("warning", "caution", "do not", "never ")):
            kind = "warning"
        elif re.search(r"```|\b(docker|kubectl|pip|npm|curl|sudo)\s+[-\w]", chunk):
            kind = "code_block"
        elif re.search(r"\b\d+(?:\.\d+)?\s*(?:%|ms|s|mb|gb|kg|ml)\b", lower):
            kind = "measurement"
        elif re.search(r"\b(is|are|means|refers to|defined as)\b", lower):
            kind = "definition"
        else:
            kind = "text"
        blocks.append({"type": kind, "content": chunk[:4000], "context_header": source_title, "position": len(blocks)})
    return blocks


def extract_atomics_from_text(user_id: str, capture_id: str, cleaned_text: str) -> list[dict]:
    """
    Extract atomics from cleaned text using AI. Creates atomics + source relations.
    If no AI configured, creates a single 'text' atomic with the full cleaned text.
    Returns list of created atomics.
    """
    capture = get_capture_ref(user_id, capture_id) or {}
    evidence = split_evidence(cleaned_text, capture.get("source_title", ""))
    for item in evidence:
        item.update({"role": "evidence", "source_id": capture_id, "extracted_by": "deterministic-evidence"})
    ids = insert_atomics_batch(user_id, evidence)
    for index, aid in enumerate(ids):
        evidence[index]["id"] = aid
        if index:
            insert_atomic_relation(user_id, ids[index - 1], aid, "precedes", 1.0,
                                   method="structural", reason="Adjacent evidence in the same capture",
                                   confidence=1.0, status="accepted")

    assignment = get_ai_assignment_for_feature(user_id, FEATURE_ATOMIC_EXTRACTION)
    provider = get_ai_provider(user_id, assignment["provider_id"]) if assignment else None
    if provider and evidence:
        numbered = "\n".join(f'{i}: {item["content"][:700]}' for i, item in enumerate(evidence))
        result = call_ai_model(provider["base_url"], decrypt_api_key(provider.get("api_key_encrypted", "")),
                               assignment["model"], [{"role":"system","content":ATOMIC_SYSTEM_PROMPT},{"role":"user","content":numbered[:8000]}], timeout=60)
        parsed = _parse_atomics_json(result or "") or []
        concept_mentions = []
        conn = get_db(user_id)
        try:
            for enrichment in parsed:
                pos = enrichment.get("position")
                if not isinstance(pos, int) or pos < 0 or pos >= len(evidence): continue
                kind = enrichment.get("type", "text")
                if kind not in {"claim","definition","procedure_step","problem","solution","outcome","warning","measurement","code_block","quote","text"}: kind="text"
                props={"summary": str(enrichment.get("summary", ""))[:500], "concepts": enrichment.get("concepts", [])[:12], "model": assignment["model"]}
                conn.execute("UPDATE atomics SET type=?,properties=?,extracted_by=?,updated_at=? WHERE id=?",(kind,json.dumps(props),"ai-enriched",datetime.now(timezone.utc).isoformat(),ids[pos]))
                evidence[pos].update({"type":kind,"properties":props,"extracted_by":"ai-enriched"})
                concept_mentions.extend((ids[pos], str(name).strip()) for name in props["concepts"] if str(name).strip())
            conn.commit()
        finally: conn.close()
        for evidence_id, name in concept_mentions:
            canonical = name.casefold()
            conn = get_db(user_id)
            try:
                row = conn.execute("SELECT id FROM atomics WHERE role='concept' AND canonical_key=?", (canonical,)).fetchone()
            finally:
                conn.close()
            concept_id = row["id"] if row else insert_atomic(
                user_id, "entity", name, properties={"entity_type":"concept","model":assignment["model"]},
                role="concept", canonical_key=canonical, extracted_by="ai-enriched",
            )
            insert_atomic_relation(
                user_id, evidence_id, concept_id, "mentions", .7,
                method="ai", reason=f"AI extracted the explicit concept {name}", confidence=.7, status="candidate",
            )
    return evidence


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
