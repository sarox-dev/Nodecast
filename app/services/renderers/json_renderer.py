"""
JSON Renderer — debug rīks, rāda KnowledgeObjects kā formatētu JSON.
"""

import json
from typing import Any

from app.services.renderers.base import BaseRenderer, register


class JsonRenderer(BaseRenderer):
    name = "json"
    label = "JSON"
    description = "Raw knowledge objects as formatted JSON (debug)"
    icon = "🔧"

    def render(self, objects: list[dict], capture_ref: dict[str, Any]) -> str:
        data = {
            "capture": {
                "id": capture_ref.get("id"),
                "title": capture_ref.get("source_title"),
                "url": capture_ref.get("source_url"),
                "type": capture_ref.get("capture_type"),
            },
            "knowledge_objects": objects,
        }
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        escaped = (pretty.replace("&", "&amp;")
                         .replace("<", "&lt;")
                         .replace(">", "&gt;"))
        return f'<pre class="json-preview"><code>{escaped}</code></pre>'


register(JsonRenderer())