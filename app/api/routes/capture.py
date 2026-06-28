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
    markdown_path: str | None = None


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
            "captured_at": request.source.captured_at or now.replace(tzinfo=None).isoformat() + "Z",
        },
        "context": {
            "before": request.context.before if request.context else "",
            "after": request.context.after if request.context else "",
            "selection_html": request.context.selection_html if request.context else "",
        },
        "saved_at": now.replace(tzinfo=None).isoformat() + "Z",
    }

    # Save as JSON file
    filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{capture_id}.json"
    filepath = CONTENTS_DIR / filename

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        os.chmod(filepath, 0o644)

        # Also save as .md if markdown_path is provided
        md_written = False
        md_path = request.markdown_path
        if md_path and md_path.strip():
            md_dir = Path(md_path.strip())
            try:
                md_dir.mkdir(parents=True, exist_ok=True)
                md_filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{capture_id}.md"
                md_filepath = md_dir / md_filename

                title = request.source.title or "Untitled"
                url = request.source.url or ""
                ctx_before = request.context.before if request.context else ""
                ctx_after = request.context.after if request.context else ""
                selection_html = request.context.selection_html if request.context else ""
                content = request.content or ""

                # Build markdown content
                md_lines = []
                md_lines.append(f"# {title}")
                md_lines.append(f"")
                md_lines.append(f"**Source:** [{url}]({url})")
                md_lines.append(f"**Captured:** {now.replace(tzinfo=None).isoformat()}")
                md_lines.append(f"")
                md_lines.append(f"---")
                md_lines.append(f"")

                if ctx_before:
                    md_lines.append(f"> {ctx_before.replace(chr(10), chr(10) + '> ')}")
                    md_lines.append(f"")

                md_lines.append(content)

                if ctx_after:
                    md_lines.append(f"")
                    md_lines.append(f"> {ctx_after.replace(chr(10), chr(10) + '> ')}")

                md_filepath.write_text("\n".join(md_lines), encoding="utf-8")
                md_written = True
            except Exception as md_err:
                print(f"Recollect: failed to write markdown: {md_err}")

        msg = "Saved to Recollect"
        if md_written:
            msg += " (+ markdown)"

        return CaptureResponse(
            success=True,
            id=capture_id,
            message=msg,
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

import re


@router.get("/local/search")
def local_search(q: str = ""):
    """Full-text search over saved captures. Simple grep-based, no index needed for MVP."""
    if not q:
        return []

    if not CONTENTS_DIR.exists():
        return []

    query_lower = q.lower().strip()
    terms = [t for t in query_lower.split() if t]
    if not terms:
        return []

    files = sorted(CONTENTS_DIR.glob("*.json"), reverse=True)
    results = []

    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            # Build searchable text from all fields
            searchable = (
                (data.get("content", "") or "") + " " +
                (data.get("source", {}).get("title", "") or "") + " " +
                (data.get("source", {}).get("site_name", "") or "") + " " +
                (data.get("source", {}).get("url", "") or "") + " " +
                (data.get("context", {}).get("before", "") or "") + " " +
                (data.get("context", {}).get("after", "") or "")
            ).lower()

            if all(t in searchable for t in terms):
                results.append({
                    "id": data.get("id"),
                    "type": "saved",
                    "title": data.get("source", {}).get("title", ""),
                    "url": data.get("source", {}).get("url", ""),
                    "content": data.get("content", ""),
                    "site_name": data.get("source", {}).get("site_name", ""),
                    "saved_at": data.get("saved_at", ""),
                    "capture_id": data.get("id"),
                    "_type": "saved",
                })

        except Exception:
            pass

    return results
