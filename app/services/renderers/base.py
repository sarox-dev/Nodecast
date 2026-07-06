"""
Rendereri — pārvērš KnowledgeObjects vizuālā formā.

Katrs Renderer ir neatkarīgs modulis. Pievienojot jaunu failu
renderers/ direktorijā un reģistrējot to __init__.py, tas
automātiski parādās Knowledge Viewer UI.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseRenderer(ABC):
    """Bāzes klase visiem Rendereriem."""

    name: str = "base"
    label: str = "Base"
    description: str = ""
    icon: str = ""

    @abstractmethod
    def render(self, objects: list[dict], capture_ref: dict[str, Any]) -> str:
        """
        Renderē KnowledgeObjects un atgriež HTML string.

        Args:
            objects: KnowledgeObjects kā dicts (no model_dump)
            capture_ref: Capture reference dict ar source_title, source_url u.c.

        Returns:
            HTML string (iekšējais saturs, bez <html>/<body> apvalka)
        """
        ...


# ─── Reģistrs ─────────────────────────────────────────────────────

_renderers: dict[str, BaseRenderer] = {}


def register(renderer: BaseRenderer):
    """Reģistrē Rendereri, lai tas būtu pieejams UI un API."""
    _renderers[renderer.name] = renderer


def get_renderer(name: str) -> BaseRenderer | None:
    """Atgriež Rendereri pēc nosaukuma."""
    return _renderers.get(name)


def list_renderers() -> list[dict]:
    """Atgriež visu Rendereru sarakstu (metadatus priekš UI)."""
    return [
        {
            "name": r.name,
            "label": r.label,
            "description": r.description,
            "icon": r.icon,
        }
        for r in _renderers.values()
    ]


def render(objects: list[dict], capture_ref: dict, renderer_name: str = "markdown") -> str:
    """Renderē ar konkrētu Rendereri. Fallback uz markdown."""
    renderer = get_renderer(renderer_name) or get_renderer("markdown")
    if not renderer:
        return "<p>No renderer available</p>"
    return renderer.render(objects, capture_ref)