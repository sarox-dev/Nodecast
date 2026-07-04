"""
Knowledge API — piekļuve KnowledgeObjects.

GET  /api/capture/{id}/knowledge    → visi KnowledgeObjects capture
GET  /api/capture/{id}/markdown     → Markdown renderējums
GET  /api/knowledge/types           → visi tipi
GET  /api/knowledge/stats           → statistika
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.services.auth import get_current_user
from app.services.knowledge_store import (
    get_knowledge_for_capture,
    get_knowledge_by_type,
    count_knowledge_objects,
    delete_knowledge_for_capture,
)
from app.services.raw_storage import get_raw_html
from app.services.database import get_capture_ref
from app.models.knowledge import KNOWLEDGE_OBJECT_TYPES

router = APIRouter()


@router.get("/api/capture/{capture_id}/knowledge")
def get_knowledge(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Atgriež visus KnowledgeObjects konkrētam capture."""
    user_id = current_user["user_id"]
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    objects = get_knowledge_for_capture(user_id, capture_id)
    return {
        "success": True,
        "capture_id": capture_id,
        "count": len(objects),
        "knowledge_objects": [ko.model_dump(exclude_none=True, mode="json") for ko in objects],
    }


@router.get("/api/capture/{capture_id}/markdown")
def get_markdown(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Atgriež Markdown renderējumu no KnowledgeObjects."""
    user_id = current_user["user_id"]
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    objects = get_knowledge_for_capture(user_id, capture_id)
    md = render_knowledge_to_markdown(objects, ref)
    return Response(content=md, media_type="text/markdown; charset=utf-8")


@router.get("/api/knowledge/types")
def list_knowledge_types():
    """Atgriež visus iespējamos KnowledgeObject tipus."""
    return {"types": KNOWLEDGE_OBJECT_TYPES}


@router.get("/api/knowledge/stats")
def knowledge_stats(current_user: dict = Depends(get_current_user)):
    """Statistika — cik kāda tipa objektu."""
    user_id = current_user["user_id"]
    return count_knowledge_objects(user_id)


@router.get("/api/knowledge/type/{type_}")
def get_by_type(type_: str, current_user: dict = Depends(get_current_user)):
    """Atgriež KnowledgeObjects pēc tipa."""
    user_id = current_user["user_id"]
    objects = get_knowledge_by_type(user_id, type_)
    return {
        "success": True,
        "type": type_,
        "count": len(objects),
        "knowledge_objects": [ko.model_dump(exclude_none=True, mode="json") for ko in objects],
    }


# ─── Markdown Renderer ───────────────────────────────────────────

def render_knowledge_to_markdown(objects: list, capture_ref: dict) -> str:
    """Pārvērš KnowledgeObjects sarakstu uz Markdown."""
    if not objects:
        return f"# {capture_ref.get('source_title', 'Untitled')}\n\n*No extracted content.*\n"

    lines: list[str] = []
    source_url = capture_ref.get("source_url", "")
    source_title = capture_ref.get("source_title", "Untitled")

    # Helper to parse tags (can be str or list)
    def _parse_tags(tags):
        if isinstance(tags, str):
            import json
            try: return json.loads(tags)
            except: return []
        return tags or []

    # Header
    lines.append(f"# {source_title}")
    if source_url:
        lines.append(f"**Source:** [{source_url}]({source_url})")
    lines.append(f"**Type:** {capture_ref.get('capture_type', 'page')}")
    if capture_ref.get("project"):
        lines.append(f"**Project:** {capture_ref['project']}")
    tags = _parse_tags(capture_ref.get("tags"))
    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}")
    lines.append(f"**Saved:** {capture_ref.get('saved_at', '')}")
    lines.append("")

    for ko in objects:
        props = ko.properties
        ko_type = ko.type

        if ko_type == "metadata":
            lines.append("---")
            lines.append("## Page Metadata")
            if props.get("title"):
                lines.append(f"- **Title:** {props['title']}")
            if props.get("description"):
                lines.append(f"- **Description:** {props['description']}")
            if props.get("keywords"):
                lines.append(f"- **Keywords:** {', '.join(props['keywords'])}")
            if props.get("author"):
                lines.append(f"- **Author:** {props['author']}")
            if props.get("language"):
                lines.append(f"- **Language:** {props['language']}")
            lines.append("")

        elif ko_type == "article":
            lines.append("---")
            lines.append("## Content")
            text = props.get("text", "")
            # Split into paragraphs
            for para in text.split("\n"):
                para = para.strip()
                if para:
                    lines.append(para)
                    lines.append("")

        elif ko_type == "heading":
            level = props.get("level", 1)
            text = props.get("text", "")
            lines.append(f"{'#' * level} {text}")
            lines.append("")

        elif ko_type == "code_block":
            lang = props.get("language", "")
            code = props.get("code", "")
            if lang:
                lines.append(f"```{lang}")
            else:
                lines.append("```")
            lines.append(code)
            lines.append("```")
            lines.append("")

        elif ko_type == "link":
            href = props.get("href", "")
            text = props.get("text", "")
            if href and text:
                lines.append(f"- [{text}]({href})")
            elif href:
                lines.append(f"- {href}")
            lines.append("")

        elif ko_type == "image":
            src = props.get("src", "")
            alt = props.get("alt", "")
            if src:
                lines.append(f"![{alt}]({src})")
                lines.append("")

        elif ko_type == "quote":
            text = props.get("text", "")
            source = props.get("source", "")
            if text:
                lines.append(f"> {text}")
                if source:
                    lines.append(f"> — {source}")
                lines.append("")

        elif ko_type == "list_item":
            text = props.get("text", "")
            if text:
                lines.append(f"- {text}")

    # Footer
    lines.append("---")
    lines.append(f"*Extracted by Recollect — {capture_ref.get('captured_at', '')}*")
    lines.append("")

    return "\n".join(lines)


import json  # noqa: E402 — imported for renderer