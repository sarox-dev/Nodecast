"""
Capture Layout API endpoints.

GET  /api/layouts                — saraksts ar visiem layoutiem
GET  /api/layouts/check?url=...  — atrod layout konkrētam URL
"""

from fastapi import APIRouter, Query, Depends
from app.services.layout_registry import list_layouts, get_layout_for_url

router = APIRouter(prefix="/api/layouts")


@router.get("")
def list_layouts_route():
    """Atgriež visu layoutu sarakstu."""
    return {"layouts": list_layouts()}


@router.get("/check")
def check_layout(url: str = Query(..., description="URL to check")):
    """
    Atrod piemērotāko Layout noteiktam URL.
    To izmanto extension, lai uzzinātu, kādas pogas rādīt.
    """
    result = get_layout_for_url(url)
    if not result.matched:
        return {"matched": False, "capture_types": [{"type": "page", "label": "Save Page", "priority": 0}]}

    return {
        "matched": True,
        "layout_name": result.layout.name if result.layout else None,
        "capture_types": [
            {
                "type": c.type,
                "label": c.label,
                "icon": c.icon,
                "selector": c.selector,
                "priority": c.priority,
            }
            for c in result.capture_types
        ],
        "collect_html": result.layout.collect_html if result.layout else True,
        "collect_metadata": result.layout.collect_metadata if result.layout else True,
    }