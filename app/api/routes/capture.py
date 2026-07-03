import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from html.parser import HTMLParser

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.services.database import get_db

router = APIRouter()
CONTENTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contents"


class SourceModel(BaseModel):
    url: str = ""
    title: str | None = None
    site_name: str | None = None
    captured_at: str | None = None


class ContextModel(BaseModel):
    before: str | None = None
    after: str | None = None
    selection_html: str | None = None
    selected_tag: str | None = None
    tag_ancestry: str | None = None


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


class TagAddRequest(BaseModel): tag: str
class TagDeleteRequest(BaseModel): tag: str
class TagRenameRequest(BaseModel): old: str; new: str
class ProjectDeleteRequest(BaseModel): name: str
class ProjectCreateRequest(BaseModel): name: str


def _row_to_dict(row) -> dict:
    tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
    return {
        "id": row["id"], "type": row["type"], "content": row["content"],
        "project": row["project"], "tags": tags,
        "source": {"url": row["source_url"], "title": row["source_title"],
                    "site_name": row["source_site_name"], "captured_at": row["source_captured_at"]},
        "context": {"before": row["context_before"], "after": row["context_after"],
                     "selection_html": row["context_selection_html"]},
        "selected_tag": row["selected_tag"] if "selected_tag" in row.keys() else "",
        "tag_ancestry": row["tag_ancestry"] if "tag_ancestry" in row.keys() else "",
        "saved_at": row["saved_at"],
    }


def _row_to_search_item(row) -> dict:
    tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
    return {
        "_type": "saved", "id": row["id"], "title": row["source_title"],
        "url": row["source_url"], "content": row["content"],
        "project": row["project"], "tags": tags,
        "context": {"before": row["context_before"], "after": row["context_after"],
                     "selection_html": row["context_selection_html"]},
        "selected_tag": row["selected_tag"] if "selected_tag" in row.keys() else "",
        "tag_ancestry": row["tag_ancestry"] if "tag_ancestry" in row.keys() else "",
        "thumbnail": None, "source": "local", "site_name": row["source_site_name"],
        "saved_at": row["saved_at"],
    }


# ─── POST /api/capture ───────────────────────────────────────────
@router.post("/capture", response_model=CaptureResponse)
def capture_item(request: CaptureRequest):
    capture_id = uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    saved_at = now.replace(tzinfo=None).isoformat() + "Z"
    tags_json = json.dumps(request.tags)

    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO items
               (id, type, content, project, tags,
                source_url, source_title, source_site_name, source_captured_at,
                context_before, context_after, context_selection_html, selected_tag, tag_ancestry, saved_at)
               VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?,?,?)""",
            (capture_id, request.type, request.content, request.project, tags_json,
             request.source.url or "", request.source.title or "", request.source.site_name or "",
             request.source.captured_at or saved_at,
             request.context.before if request.context else "",
             request.context.after if request.context else "",
             request.context.selection_html if request.context else "",
             request.context.selected_tag if request.context else "",
             request.context.tag_ancestry if request.context else "",
             saved_at),
        )
        if request.project:
            conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (request.project,))
        conn.commit()
    finally:
        conn.close()

    md_written = False
    if request.markdown_path and request.markdown_path.strip():
        md_dir = Path(request.markdown_path.strip())
        try:
            md_dir.mkdir(parents=True, exist_ok=True)
            md_filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{capture_id}.md"
            title = request.source.title or "Untitled"
            url = request.source.url or ""
            content = request.content or ""
            md_lines = [f"# {title}", "", f"**Source:** [{url}]({url})",
                        f"**Captured:** {saved_at}", "", "---", "", content]
            if request.tags:
                md_lines.insert(3, f"**Tags:** {', '.join(request.tags)}")
            md_dir.joinpath(md_filename).write_text("\n".join(md_lines), encoding="utf-8")
            md_written = True
        except Exception:
            pass

    msg = "Saved to Recollect"
    if md_written:
        msg += " (+ markdown)"
    return CaptureResponse(success=True, id=capture_id, message=msg, path=str(capture_id))


# ─── PATCH /api/capture/{capture_id} ─────────────────────────────
@router.patch("/capture/{capture_id}")
def update_capture(capture_id: str, update: UpdateRequest):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM items WHERE id=?", (capture_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Capture not found")
        data = _row_to_dict(row)
        if update.project is not None:
            data["project"] = update.project
        if update.tags is not None:
            data["tags"] = update.tags
        conn.execute("UPDATE items SET project=?, tags=? WHERE id=?",
                     (update.project if update.project is not None else data["project"],
                      json.dumps(update.tags if update.tags is not None else data["tags"]),
                      capture_id))
        conn.commit()
        return {"success": True, "id": capture_id, "project": data["project"], "tags": data["tags"]}
    finally:
        conn.close()


# ─── DELETE /api/capture/{capture_id} ─────────────────────────────
@router.delete("/capture/{capture_id}")
def delete_capture(capture_id: str):
    conn = get_db()
    try:
        if not conn.execute("SELECT id FROM items WHERE id=?", (capture_id,)).fetchone():
            raise HTTPException(404, "Capture not found")
        conn.execute("DELETE FROM items WHERE id=?", (capture_id,))
        conn.commit()
        return {"success": True, "id": capture_id}
    finally:
        conn.close()


# ─── GET /api/capture ────────────────────────────────────────────
@router.get("/capture")
def list_captures():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM items ORDER BY saved_at DESC LIMIT 50").fetchall()
        captures = []
        for row in rows:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
            captures.append({
                "id": row["id"], "type": row["type"],
                "content_preview": (row["content"] or "")[:120],
                "source_title": row["source_title"], "source_url": row["source_url"],
                "saved_at": row["saved_at"], "project": row["project"], "tags": tags,
            })
        return {"captures": captures}
    finally:
        conn.close()


# ─── GET /api/tags ───────────────────────────────────────────────
@router.get("/tags")
def get_tags():
    conn = get_db()
    try:
        rows = conn.execute("SELECT project, tags FROM items").fetchall()
        projects = {}
        all_tags = set()
        for row in rows:
            p = (row["project"] or "").strip()
            if p:
                projects[p] = projects.get(p, 0) + 1
            for t in (json.loads(row["tags"]) if isinstance(row["tags"], str) else []):
                if t.strip():
                    all_tags.add(t.strip())
        for pr in conn.execute("SELECT name FROM projects").fetchall():
            pn = (pr["name"] or "").strip()
            if pn:
                projects.setdefault(pn, 0)

        total = conn.execute("SELECT COUNT(*) as c FROM items").fetchone()["c"] or 0
        uncat = conn.execute("""SELECT COUNT(*) as c FROM items
            WHERE (project IS NULL OR project = '') AND (tags IS NULL OR tags = '[]')""").fetchone()["c"] or 0

        return {"total_items": total, "uncategorized": uncat,
                "projects": [{"name": k, "count": v} for k, v in sorted(projects.items())],
                "tags": sorted(all_tags)}
    finally:
        conn.close()


# ─── POST /api/projects ──────────────────────────────────────────
@router.post("/projects")
def create_project(request: ProjectCreateRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")
    conn = get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (name,))
        conn.commit()
        return {"success": True, "created": True, "name": name}
    finally:
        conn.close()


# ─── POST /api/projects/delete ────────────────────────────────────
@router.post("/projects/delete")
def delete_project(request: ProjectDeleteRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")
    if name.lower() in ("all items", "uncategorized"):
        raise HTTPException(400, "Cannot delete a built-in filter")
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) as c FROM items WHERE LOWER(project)=LOWER(?)", (name,)).fetchone()["c"] or 0
        conn.execute("UPDATE items SET project='' WHERE LOWER(project)=LOWER(?)", (name,))
        conn.execute("DELETE FROM projects WHERE LOWER(name)=LOWER(?)", (name,))
        conn.commit()
        return {"success": True, "message": f"Removed project '{name}' from {count} item(s)."}
    finally:
        conn.close()


# ─── POST /api/tags/add ───────────────────────────────────────────
@router.post("/tags/add")
def add_tag(request: TagAddRequest):
    return {"success": True, "message": f"Tag '{request.tag}' is available."}


# ─── POST /api/tags/delete ────────────────────────────────────────
@router.post("/tags/delete")
def delete_tag(request: TagDeleteRequest):
    tag = request.tag.strip()
    if not tag:
        raise HTTPException(400, "Tag name is required")
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, tags FROM items").fetchall()
        count = 0
        for row in rows:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
            if tag in tags:
                conn.execute("UPDATE items SET tags=? WHERE id=?", (json.dumps([t for t in tags if t != tag]), row["id"]))
                count += 1
        conn.commit()
        return {"success": True, "message": f"Removed '{tag}' from {count} item(s)."}
    finally:
        conn.close()


# ─── POST /api/tags/rename ────────────────────────────────────────
@router.post("/tags/rename")
def rename_tag(request: TagRenameRequest):
    old = request.old.strip()
    new = request.new.strip()
    if not old or not new:
        raise HTTPException(400, "Both old and new tag names required")
    if old == new:
        return {"success": True, "message": "No change needed."}
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, tags FROM items").fetchall()
        count = 0
        for row in rows:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
            if old in tags:
                conn.execute("UPDATE items SET tags=? WHERE id=?", (json.dumps([new if t == old else t for t in tags]), row["id"]))
                count += 1
        conn.commit()
        return {"success": True, "message": f"Renamed '{old}' to '{new}' in {count} item(s)."}
    finally:
        conn.close()


# ─── Bookmark import ─────────────────────────────────────────────
class BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self.folder_stack = [""]
        self._in_h3 = self._in_a = False
        self._current_entry = None
        self._h3_text = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        ad = dict(attrs)
        if tag == "h3":
            self._in_h3 = True; self._h3_text = ""
        if tag == "a" and ad.get("href"):
            self.bookmarks.append({"title": "", "url": ad["href"],
                "folder": "/".join(self.folder_stack), "tags_str": ad.get("tags", "")})
            self._current_entry = len(self.bookmarks) - 1; self._in_a = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "h3" and self._h3_text.strip():
            self.folder_stack.append(self._h3_text.strip())
            self._in_h3 = False; self._h3_text = ""
        if tag == "a": self._in_a = False; self._current_entry = None

    def handle_data(self, data):
        t = data.strip()
        if not t: return
        if self._in_h3: self._h3_text += t
        if self._current_entry is not None and self._in_a:
            self.bookmarks[self._current_entry]["title"] = (self.bookmarks[self._current_entry]["title"] + t).strip()


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
    saved_at = now.replace(tzinfo=None).isoformat() + "Z"
    saved = []
    errors = 0
    conn = get_db()
    try:
        for bm in bookmarks:
            capture_id = uuid4().hex[:12]
            tags = [t.strip() for t in bm["folder"].split("/") if t.strip()] if bm["folder"] else []
            if bm["tags_str"]:
                tags.extend(t.strip() for t in bm["tags_str"].split(",") if t.strip())
            project = folders[0] if (folders := [f.strip() for f in bm["folder"].split("/") if f.strip()]) else ""
            tags = folders[1:] + tags if folders else tags
            try:
                conn.execute(
                    """INSERT INTO items (id, type, content, project, tags,
                       source_url, source_title, source_site_name, source_captured_at,
                       context_before, context_after, context_selection_html, selected_tag, tag_ancestry, saved_at)
                       VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?,?,?)""",
                    (capture_id, "bookmark", bm["title"], project, json.dumps(tags),
                     bm["url"], bm["title"], "", saved_at,
                     "", "", "", "", "", saved_at))
                saved.append({"title": bm["title"], "url": bm["url"], "project": project, "tags": tags})
            except Exception:
                errors += 1
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "total": len(bookmarks), "saved": len(saved), "errors": errors, "items": saved[:50]}


def parse_bookmark_html(content: str) -> list[dict]:
    parser = BookmarkParser()
    parser.feed(content)
    return parser.bookmarks


# ─── GET /api/local/search ────────────────────────────────────────
@router.get("/local/search")
def local_search(q: str = ""):
    if not q:
        return []
    terms = [t for t in q.lower().strip().split() if t]
    if not terms:
        return []
    conn = get_db()
    try:
        results = []
        for row in conn.execute("SELECT * FROM items ORDER BY saved_at DESC").fetchall():
            searchable = (" ".join([row["content"] or "", row["source_title"] or "",
                row["source_site_name"] or "", row["source_url"] or "",
                row["context_before"] or "", row["context_after"] or "",
                row["project"] or ""])).lower()
            try:
                searchable += " " + " ".join(json.loads(row["tags"]) if isinstance(row["tags"], str) else [])
            except Exception:
                pass
            if all(t in searchable for t in terms):
                results.append({
                    "id": row["id"], "type": "saved", "title": row["source_title"],
                    "url": row["source_url"], "content": row["content"],
                    "site_name": row["source_site_name"], "saved_at": row["saved_at"],
                    "capture_id": row["id"], "project": row["project"],
                    "tags": json.loads(row["tags"]) if isinstance(row["tags"], str) else [],
                    "_type": "saved",
                })
        return results
    finally:
        conn.close()
