import os
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

CONTENTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contents"
CONTENTS_DIR.mkdir(exist_ok=True)


class SourceModel(BaseModel):
    url: str
    title: str | None = None
    site_name: str | None = None
    captured_at: str | None = None


class ContextModel(BaseModel):
    before: str | None = None
    after: str | None = None
    selection_html: str | None = None


class CaptureRequest(BaseModel):
    type: str = "snippet"
    content: str
    source: SourceModel
    context: ContextModel | None = None


class CaptureResponse(BaseModel):
    success: bool
    id: str
    message: str
    path: str | None = None


@router.post("/capture", response_model=CaptureResponse)
def capture_item(request: CaptureRequest):
    """Receive captured content from the browser extension and save it locally."""
    capture_id = uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    # Build the saved record
    record = {
        "id": capture_id,
        "type": request.type,
        "content": request.content,
        "source": {
            "url": request.source.url,
            "title": request.source.title or "",
            "site_name": request.source.site_name or "",
            "captured_at": request.source.captured_at or now.isoformat() + "Z",
        },
        "context": {
            "before": request.context.before if request.context else "",
            "after": request.context.after if request.context else "",
            "selection_html": request.context.selection_html if request.context else "",
        },
        "saved_at": now.isoformat() + "Z",
    }

    # Save as JSON file
    filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{capture_id}.json"
    filepath = CONTENTS_DIR / filename

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        os.chmod(filepath, 0o644)

        return CaptureResponse(
            success=True,
            id=capture_id,
            message="Saved to Recollect",
            path=str(filepath),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@router.get("/capture")
def list_captures():
    """List all saved captures (for debugging / MVP visibility)."""
    if not CONTENTS_DIR.exists():
        return {"captures": []}

    files = sorted(CONTENTS_DIR.glob("*.json"), reverse=True)
    captures = []
    for f in files[:50]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                captures.append({
                    "id": data.get("id"),
                    "type": data.get("type"),
                    "content_preview": data.get("content", "")[:120],
                    "source_title": data.get("source", {}).get("title", ""),
                    "source_url": data.get("source", {}).get("url", ""),
                    "saved_at": data.get("saved_at", ""),
                })
        except Exception:
            pass

    return {"captures": captures}
