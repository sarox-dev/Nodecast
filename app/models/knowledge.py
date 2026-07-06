"""
Knowledge Objects — atomiskas zināšanu vienības.

Viens CapturePackage → Extractor → daudzi KnowledgeObjects.
Katrs KnowledgeObject apraksta vienu atomisku objektu (article, heading, link, code_block...).
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class KnowledgeObject(BaseModel):
    """Viena atomiska zināšanu vienība, kas iegūta no CapturePackage."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    capture_id: str = ""
    """FK uz captures tabulu"""

    type: str = ""
    """Tips: article | heading | link | code_block | image | metadata | list_item | ..."""

    properties: dict[str, Any] = Field(default_factory=dict)
    """Tipam specifiski dati. Atkarīgs no type."""

    confidence: float = 1.0
    """Cik drošs ir Extractor ka šis objekts ir korekts (0.0 - 1.0)"""

    extracted_by: str = ""
    """Extractor vārds, kas radīja šo objektu (piem., 'generic-html')"""

    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    position: int = 0
    """Secība capture ietvaros"""


# ─── Extractor rezultāts ─────────────────────────────────────────

class ExtractorResult(BaseModel):
    """Extractor pipeline rezultāts — satur visus atrastos KnowledgeObjects."""

    knowledge_objects: list[KnowledgeObject] = Field(default_factory=list)
    confidence: float = 1.0
    extractor_version: str = "1.0"
    warnings: list[str] = Field(default_factory=list)


# ─── Tips — dokumentācijai un tipu sarakstam ─────────────────────

KNOWLEDGE_OBJECT_TYPES: dict[str, dict[str, str]] = {
    "article": {
        "description": "Galvenais satura bloks — teksts, virsraksts, autors",
        "properties": "title, text, author, published_at, word_count",
    },
    "heading": {
        "description": "Virsraksts (h1-h6)",
        "properties": "level (int), text",
    },
    "link": {
        "description": "Atsauce uz citu resursu",
        "properties": "href, text, rel",
    },
    "code_block": {
        "description": "Koda bloks",
        "properties": "language, code",
    },
    "image": {
        "description": "Attēls",
        "properties": "src, alt, width, height",
    },
    "metadata": {
        "description": "Lapas metadati — title, description, keywords",
        "properties": "title, description, keywords[], author, language",
    },
    "list_item": {
        "description": "Viens saraksta elements",
        "properties": "text, list_type (ul|ol), parent_list",
    },
    "quote": {
        "description": "Citāts no lapas",
        "properties": "text, author, source",
    },
    "video": {
        "description": "Video informācija (YouTube u.c.)",
        "properties": "video_id, title, author, duration_seconds, description, keywords, publish_date",
    },
    "reddit_post": {
        "description": "Reddit post — tikai saturs, bez komentāriem",
        "properties": "title, author, subreddit, score, timestamp, comments_count, url",
    },
    "json_ld": {
        "description": "Schema.org JSON-LD dati",
        "properties": "schema_type, data",
    },
    "document": {
        "description": "DOM secīgi satura bloki — headings, paragraphs, images, code, tables, lists",
        "properties": "title, blocks[], block_count",
    },
}