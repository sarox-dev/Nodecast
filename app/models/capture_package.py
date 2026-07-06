"""
Capture Package — vienotais sūtīšanas formāts (Fāze 1).

Pilna specifikācija: AI_Vault/Recollect/Architecture/CapturePackage.md
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


# ─── Source ───────────────────────────────────────────────────────

class SourceInfo(BaseModel):
    url: str = ""
    title: str | None = None
    site_name: str | None = None
    extension_version: str | None = None
    browser: str | None = None
    user_agent: str | None = None


# ─── Page Metadata ────────────────────────────────────────────────

class PageMetadata(BaseModel):
    canonical: str | None = None
    language: str | None = None
    charset: str | None = None
    content_type: str | None = None
    favicon: str | None = None
    open_graph: dict[str, Any] = Field(default_factory=dict)
    twitter_card: dict[str, Any] = Field(default_factory=dict)
    schema_org: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_none_to_default(cls, data: Any) -> Any:
        """Pārvērš null/None vērtības par noklusējuma tukšām vērtībām."""
        if not isinstance(data, dict):
            return data
        if data.get("open_graph") is None:
            data["open_graph"] = {}
        if data.get("twitter_card") is None:
            data["twitter_card"] = {}
        if data.get("schema_org") is None:
            data["schema_org"] = []
        return data


# ─── Anchor (replaces old selected_element) ──────────────────────

class Anchor(BaseModel):
    selected_text: str | None = None
    css_selector: str | None = None
    xpath: str | None = None
    selection_html: str | None = None
    tag_ancestry: list[str] = Field(default_factory=list)
    selected_tag: str | None = None
    before_text: str | None = None
    after_text: str | None = None


# ─── Capture Package ─────────────────────────────────────────────

class CapturePackage(BaseModel):
    version: str = "1.0"
    capture_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    captured_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    capture_type: str = "page"  # page | article | video | issue | chat | pdf | snippet | ...

    source: SourceInfo = Field(default_factory=SourceInfo)
    page_metadata: PageMetadata | None = None
    anchor: Anchor | None = None

    tags: list[str] = Field(default_factory=list)
    project: str = ""


# ─── Response ─────────────────────────────────────────────────────

class CaptureResponse(BaseModel):
    success: bool
    id: str
    message: str