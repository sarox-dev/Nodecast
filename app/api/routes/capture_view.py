"""
Capture View — Web UI priekš Knowledge Viewer (izstrādātāja rīks).

GET /capture/{capture_id} → Jinja2 template ar 5 tabiem
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services.auth import get_user_from_cookie
from app.services.database import get_capture_ref, user_count, get_capture_ai_tags, get_entities_for_capture
from app.services.knowledge_store import get_knowledge_for_capture
from app.services.raw_storage import load_raw_capture, get_raw_html
from app.services.renderers import render, list_renderers

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/capture/{capture_id}")
async def capture_view(
    request: Request,
    capture_id: str,
):
    """Knowledge Viewer lapa — 5 tabi: Overview, Renderers, Knowledge, Raw, History."""

    # Auth check — try cookie first, then Bearer header
    user = await get_user_from_cookie(request)

    if not user:
        # Try Bearer from raw header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:]
            from app.services.auth import decode_token
            payload = decode_token(token_str)
            if payload:
                user = {"user_id": payload["sub"], "username": payload["username"]}

    if not user:
        return RedirectResponse(url="/login")

    user_id = user["user_id"]

    # Load basic capture info and knowledge (NOT RAW — lazy loaded)
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        return templates.TemplateResponse(request, "capture_view.html", {
            "error": "Capture not found",
            "capture": {},
            "knowledge_objects": [],
            "rendered_html": "",
            "renderers": list_renderers(),
            "has_html": False,
            "user": user,
        })

    objects = get_knowledge_for_capture(user_id, capture_id)
    objects_dict = [ko.model_dump(exclude_none=True, mode="json") for ko in objects]

    # Pre-render default (markdown) for the Renderers tab
    rendered_html = render(objects_dict, dict(ref))

    # Load AI tags
    ai_tags = get_capture_ai_tags(user_id, capture_id)

    # Load entities linked to this capture
    entities = get_entities_for_capture(user_id, capture_id)

    return templates.TemplateResponse(request, "capture_view.html", {
        "capture": dict(ref),
        "knowledge_objects": objects_dict,
        "rendered_html": rendered_html,
        "renderers": list_renderers(),
        "has_html": False,  # Will be checked on lazy load
        "user": user,
        "error": None,
        "ai_tags": ai_tags,
        "entities": entities,
    })