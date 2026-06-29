import os
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from html.parser import HTMLParser

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter()

CONTENTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contents"
CONTENTS_DIR.mkdir(exist_ok=True)


class SourceModel(BaseModel):
    url: str = ""
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
    source: SourceModel = SourceModel()
    context: ContextModel | None = None
    markdown_path: str | None = None
    tags: list[str] = []


class CaptureResponse(BaseModel):
    success: bool
    id: str
    message: str
    path: str | None = None


@router.post("/capture", response_model=CaptureResponse)
def capture_item(request: CaptureRequest):
    """Receive captured content from browser extension or manual form and save it locally."""
    capture_id = uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    record = {
        "id": capture_id,
        "type": request.type,
        "content": request.content,
        "tags": request.tags,
        "source": {
            "url": request.source.url or "",
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
                content = request.content or ""

                md_lines = [
                    f"# {title}",
                    "",
                    f"**Source:** [{url}]({url})",
                    f"**Captured:** {now.replace(tzinfo=None).isoformat()}",
                    "",
                    "---",
                    "",
                    content,
                ]

                if request.tags:
                    md_lines.insert(3, f"**Tags:** {', '.join(request.tags)}")

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


# ─── Bookmark HTML parser ───────────────────────────────────────

class BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self.folder_stack = [""]
        self._in_h3 = False
        self._in_a = False
        self._current_entry = None
        self._h3_text = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if tag == "h3":
            self._in_h3 = True
            self._h3_text = ""
        if tag == "a":
            href = attrs_dict.get("href", "")
            tags = attrs_dict.get("tags", "")
            if href:
                current_folder = "/".join(self.folder_stack)
                self.bookmarks.append({
                    "title": "",
                    "url": href,
                    "folder": current_folder,
                    "tags_str": tags,
                })
                self._current_entry = len(self.bookmarks) - 1
                self._in_a = True
            else:
                self._current_entry = None

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "h3":
            if self._h3_text.strip():
                self.folder_stack.append(self._h3_text.strip())
            self._in_h3 = False
            self._h3_text = ""
        if tag == "a":
            self._in_a = False
            self._current_entry = None

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self._in_h3:
            self._h3_text += text
        if self._current_entry is not None and self._in_a:
            entry = self.bookmarks[self._current_entry]
            entry["title"] = (entry["title"] + text).strip()


def parse_bookmark_html(content: str) -> list[dict]:
    parser = BookmarkParser()
    parser.feed(content)
    return parser.bookmarks


# ─── Import endpoint ────────────────────────────────────────────

@router.post("/import/bookmarks")
def import_bookmarks(file: UploadFile = File(...)):
    """Import bookmarks from a Netscape-format HTML file (browser export)."""
    if not file.filename or not file.filename.endswith(".html"):
        raise HTTPException(400, "Please upload an .html bookmark file")

    try:
        raw = file.file.read().decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(400, "Could not read file")

    bookmarks = parse_bookmark_html(raw)

    if not bookmarks:
        raise HTTPException(400, "No bookmarks found in file")

    now = datetime.now(timezone.utc)
    saved = []
    errors = 0

    for bm in bookmarks:
        capture_id = uuid4().hex[:12]
        tags = []
        if bm["folder"]:
            tags = [t.strip() for t in bm["folder"].split("/") if t.strip()]
        if bm["tags_str"]:
            tags.extend([t.strip() for t in bm["tags_str"].split(",") if t.strip()])

        record = {
            "id": capture_id,
            "type": "bookmark",
            "content": bm["title"],
            "tags": tags,
            "source": {
                "url": bm["url"],
                "title": bm["title"],
                "site_name": "",
                "captured_at": now.replace(tzinfo=None).isoformat() + "Z",
            },
            "context": {"before": "", "after": "", "selection_html": ""},
            "saved_at": now.replace(tzinfo=None).isoformat() + "Z",
        }

        try:
            filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{capture_id}.json"
            filepath = CONTENTS_DIR / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            os.chmod(filepath, 0o644)
            saved.append({"title": bm["title"], "url": bm["url"], "tags": tags})
        except Exception:
            errors += 1

    return {
        "success": True,
        "total": len(bookmarks),
        "saved": len(saved),
        "errors": errors,
        "items": saved[:50],  # preview first 50
    }


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
                    "tags": data.get("tags", []),
                })
        except Exception:
            pass

    return {"captures": captures}


import re


@router.get("/local/search")
def local_search(q: str = ""):
    """Full-text search over saved captures."""
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

            searchable = (
                (data.get("content", "") or "") + " " +
                (data.get("source", {}).get("title", "") or "") + " " +
                (data.get("source", {}).get("site_name", "") or "") + " " +
                (data.get("source", {}).get("url", "") or "") + " " +
                (data.get("context", {}).get("before", "") or "") + " " +
                (data.get("context", {}).get("after", "") or "") + " " +
                " ".join(data.get("tags", []))
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
                    "tags": data.get("tags", []),
                    "_type": "saved",
                })

        except Exception:
            pass

    return results