"""
Renderer reģistrs — automātiski importē visus rendererus no šīs mapes.

Pievienojot jaunu .py failu šeit (ar BaseRenderer subclass un register() call),
tas automātiski būs pieejams UI / API.
"""

from app.services.renderers.base import (
    BaseRenderer,
    register,
    list_renderers,
    get_renderer,
    render,
)

# ─── Importēt visus rendererus (tie paši sevi reģistrē) ──────────

from app.services.renderers import markdown  # noqa: F401
from app.services.renderers import json_renderer  # noqa: F401

__all__ = ["BaseRenderer", "register", "list_renderers", "get_renderer", "render"]