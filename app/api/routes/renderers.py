"""
Renderer API — piekļuve Rendereriem.

GET  /api/renderers                    → saraksts ar visiem
GET  /api/capture/{id}/render/{name}  → renderē ar konkrēto
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.services.auth import get_current_user
from app.services.knowledge_store import get_knowledge_for_capture
from app.services.database import get_capture_ref
from app.services.renderers import list_renderers, get_renderer

router = APIRouter(prefix="/api")


@router.get("/renderers")
def list_all_renderers():
    """Atgriež visu pieejamo Rendereru sarakstu."""
    return {"renderers": list_renderers()}


@router.get("/capture/{capture_id}/render/{renderer_name}", response_class=HTMLResponse)
def render_capture(
    capture_id: str,
    renderer_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Renderē capture ar konkrēto Rendereri. Atgriež HTML."""
    user_id = current_user["user_id"]

    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    renderer = get_renderer(renderer_name)
    if not renderer:
        raise HTTPException(404, f"Renderer '{renderer_name}' not found")

    objects = get_knowledge_for_capture(user_id, capture_id)
    objects_dict = [ko.model_dump(exclude_none=True, mode="json") for ko in objects]
    ref_dict = dict(ref)

    html = renderer.render(objects_dict, ref_dict)
    return html