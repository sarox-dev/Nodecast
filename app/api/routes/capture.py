import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from html.parser import HTMLParser

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter()

CONTENTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contents"
CONTENTS_DIR.mkdir(exist_ok=True)
PROJECTS_FILE = CONTENTS_DIR / "projects.json"


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
    project: str = ""


class CaptureResponse(BaseModel):
    success: bool
    id: str
    message: str
    path: str | None = None


class UpdateRequest(BaseModel):
    project: str | None = None
    tags: list[str] | None = None


class ProjectCreateRequest(BaseModel):
    name: str


def _load_all_files():
    """Load all saved JSON files, newest first."""
    if not CONTENTS_DIR.exists():
        return []
    files = sorted(CONTENTS_DIR.glob("*.json"), reverse=True)
    result = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                result.append((f, json.load(fh)))
        except Exception:
            pass
    return result


def _save_file(filepath, record):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.chmod(filepath, 0o644)


def _load_projects():
    if not PROJECTS_FILE.exists():
        return []
    try:
        with open(PROJECTS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            items = data.get("projects", [])
        elif isinstance(data, list):
            items = data
        else:
            return []
        return [str(item).strip() for item in items if str(item).strip()]
    except Exception:
        return []


def _save_projects(projects):
    payload = {"projects": projects}
    with open(PROJECTS_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.chmod(PROJECTS_FILE, 0o644)


def _matches_project_filter(data, project_filter):
    if not project_filter:
        return True
    if project_filter == "__uncategorized__":
        project_name = str(data.get("project", "")).strip()
        tags = [str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()]
        return not project_name and not tags
    return str(data.get("project", "")).strip().lower() == project_filter.lower()


# ─── POST /api/capture ───────────────────────────────────────────

@router.post("/capture", response_model=CaptureResponse)
def capture_item(request: CaptureRequest):
    capture_id = uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    record = {
        "id": capture_id,
        "type": request.type,
        "content": request.content,
        "project": request.project,
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
        _save_file(filepath, record)

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
                    f"# {title}", "",
                    f"**Source:** [{url}]({url})",
                    f"**Captured:** {now.replace(tzinfo=None).isoformat()}",
                    "", "---", "", content,
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

        return CaptureResponse(success=True, id=capture_id, message=msg, path=str(filepath))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


# ─── PATCH /api/capture/{capture_id} ─────────────────────────────

@router.patch("/capture/{capture_id}")
def update_capture(capture_id: str, update: UpdateRequest):
    """Update project and/or tags of an existing capture."""
    for filepath, data in _load_all_files():
        if data.get("id") == capture_id:
            changed = False
            if update.project is not None:
                data["project"] = update.project
                changed = True
            if update.tags is not None:
                data["tags"] = update.tags
                changed = True
            if not changed:
                raise HTTPException(400, "Nothing to update")
            _save_file(filepath, data)
            return {"success": True, "id": capture_id, "project": data.get("project", ""), "tags": data.get("tags", [])}

    raise HTTPException(404, "Capture not found")


@router.delete("/capture/{capture_id}")
def delete_capture(capture_id: str):
    """Delete an existing capture."""
    for filepath, data in _load_all_files():
        if data.get("id") == capture_id:
            try:
                filepath.unlink(missing_ok=True)
                return {"success": True, "id": capture_id}
            except Exception as exc:
                raise HTTPException(500, f"Failed to delete: {str(exc)}") from exc

    raise HTTPException(404, "Capture not found")


# ─── GET /api/tags ───────────────────────────────────────────────

@router.get("/tags")
def get_tags():
    """Return all known projects and tags across all saved items."""
    projects = {}
    all_tags = set()

    for _, data in _load_all_files():
        p = data.get("project", "").strip()
        if p:
            projects[p] = projects.get(p, 0) + 1
        for t in data.get("tags", []):
            t = t.strip()
            if t:
                all_tags.add(t)

    for project_name in _load_projects():
        projects.setdefault(project_name, 0)

    total = len(list(CONTENTS_DIR.glob("*.json")))
    uncategorized = sum(
        1
        for _, data in _load_all_files()
        if not str(data.get("project", "")).strip() and not any(str(tag).strip() for tag in data.get("tags", []))
    )

    return {
        "total_items": total,
        "uncategorized": uncategorized,
        "projects": [{"name": k, "count": v} for k, v in sorted(projects.items())],
        "tags": sorted(all_tags),
    }


@router.post("/projects")
def create_project(request: ProjectCreateRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")

    projects = _load_projects()
    if name.lower() in {project.lower() for project in projects}:
        return {"success": True, "created": False, "name": name}

    projects.append(name)
    _save_projects(projects)
    return {"success": True, "created": True, "name": name}


# ─── Bookmark import ─────────────────────────────────────────────

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


@router.post("/import/bookmarks")
def import_bookmarks(file: UploadFile = File(...)):
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

        # First folder level becomes project, rest are tags
        project = ""
        if bm["folder"]:
            folders = [f.strip() for f in bm["folder"].split("/") if f.strip()]
            project = folders[0]
            tags = folders[1:] + tags

        record = {
            "id": capture_id, "type": "bookmark", "content": bm["title"],
            "project": project, "tags": tags,
            "source": {"url": bm["url"], "title": bm["title"], "site_name": "",
                       "captured_at": now.replace(tzinfo=None).isoformat() + "Z"},
            "context": {"before": "", "after": "", "selection_html": ""},
            "saved_at": now.replace(tzinfo=None).isoformat() + "Z",
        }

        try:
            filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{capture_id}.json"
            filepath = CONTENTS_DIR / filename
            _save_file(filepath, record)
            saved.append({"title": bm["title"], "url": bm["url"], "project": project, "tags": tags})
        except Exception:
            errors += 1

    return {"success": True, "total": len(bookmarks), "saved": len(saved), "errors": errors, "items": saved[:50]}


# ─── GET /api/capture ────────────────────────────────────────────

@router.get("/capture")
def list_captures():
    if not CONTENTS_DIR.exists():
        return {"captures": []}
    files = sorted(CONTENTS_DIR.glob("*.json"), reverse=True)
    captures = []
    for f in files[:50]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                captures.append({
                    "id": data.get("id"), "type": data.get("type"),
                    "content_preview": data.get("content", "")[:120],
                    "source_title": data.get("source", {}).get("title", ""),
                    "source_url": data.get("source", {}).get("url", ""),
                    "saved_at": data.get("saved_at", ""),
                    "project": data.get("project", ""),
                    "tags": data.get("tags", []),
                })
        except Exception:
            pass
    return {"captures": captures}


# ─── GET /api/local/search ───────────────────────────────────────

@router.get("/local/search")
def local_search(q: str = ""):
    if not q or not CONTENTS_DIR.exists():
        return []

    terms = [t for t in q.lower().strip().split() if t]
    if not terms:
        return []

    results = []
    for f in sorted(CONTENTS_DIR.glob("*.json"), reverse=True):
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
                " ".join(data.get("tags", [])) + " " +
                (data.get("project", "") or "")
            ).lower()

            if all(t in searchable for t in terms):
                results.append({
                    "id": data.get("id"), "type": "saved",
                    "title": data.get("source", {}).get("title", ""),
                    "url": data.get("source", {}).get("url", ""),
                    "content": data.get("content", ""),
                    "site_name": data.get("source", {}).get("site_name", ""),
                    "saved_at": data.get("saved_at", ""),
                    "capture_id": data.get("id"),
                    "project": data.get("project", ""),
                    "tags": data.get("tags", []),
                    "_type": "saved",
                })
        except Exception:
            pass
    return results