import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.models.capture_package import CapturePackage, CaptureResponse as CPResponse
from app.services.database import (
    get_db,
    get_capture_ref,
    insert_capture_ref,
    list_captures,
    delete_capture_ref,
    search_captures,
)
from app.services.raw_storage import (
    save_raw_capture,
    load_raw_capture,
    get_raw_html,
    list_raw_captures,
    raw_exists,
)
from app.services.extractor_pipeline import extract_and_save
from app.services.ai_tagging import tag_capture, summarize_capture
from app.services.entity_extraction import extract_entities
from app.services.ai_batch import add_pending_jobs_on_save
from app.services.knowledge_store import delete_knowledge_for_capture
from app.services.raw_storage import get_raw_html, load_raw_capture
from app.services.auth import get_current_user, get_optional_user

router = APIRouter()


# ─── Helper: add Content-Type for JSON responses ──────────────────

from fastapi.responses import JSONResponse, Response


# ─── POST /api/capture ────────────────────────────────────────────

@router.post("/capture", response_model=CPResponse)
def capture_item(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    saved_at = now.isoformat().replace("+00:00", "Z")

    # Extract page_html from body (optional), remove before validation
    page_html = body.pop("page_html", None)

    # Validate as CapturePackage
    try:
        package = CapturePackage(**body)
    except Exception as e:
        raise HTTPException(422, f"Invalid Capture Package: {e}")

    # Ensure captured_at is set
    if not package.captured_at:
        package.captured_at = saved_at

    # Save raw capture to filesystem (immutable)
    try:
        raw_path = save_raw_capture(user_id, package, html=page_html)
    except FileExistsError as e:
        raise HTTPException(409, str(e))

    # Save reference in user's SQLite
    insert_capture_ref(
        user_id=user_id,
        capture_id=package.capture_id,
        capture_type=package.capture_type,
        source_url=package.source.url,
        source_title=package.source.title,
        source_site_name=package.source.site_name,
        captured_at=package.captured_at,
        saved_at=saved_at,
        tags=package.tags,
        project=package.project,
        raw_path=str(raw_path),
    )

    # Run Extractor pipeline (non-blocking — produce Knowledge Objects)
    extraction = None
    try:
        extraction = extract_and_save(user_id, package, html=page_html)
    except Exception:
        pass  # Extraction failure shouldn't break the save

    msg = f"Saved to Nodecast ({package.capture_type})"
    if extraction and extraction.knowledge_objects:
        msg += f" — extracted {len(extraction.knowledge_objects)} knowledge objects"

    # Enqueue AI processing jobs (processed in batch by model group)
    try:
        add_pending_jobs_on_save(user_id, package.capture_id)
    except Exception:
        pass  # Enqueue failure shouldn't break the save

    return CPResponse(
        success=True,
        id=package.capture_id,
        message=msg,
    )


# ─── GET /api/capture/{capture_id} ────────────────────────────────
# Returns the full CapturePackage (from raw filesystem)

@router.get("/capture/{capture_id}")
def get_capture(capture_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    raw = load_raw_capture(user_id, capture_id)
    if not raw:
        raise HTTPException(404, "Raw capture data not found")

    return {
        "success": True,
        "capture": raw.model_dump(exclude_none=True, mode="json"),
        "has_html": (Path(ref["raw_path"]) / "page.html").exists(),
    }


# ─── GET /api/capture/{capture_id}/page.html ──────────────────────
# Returns the original page HTML

@router.get("/capture/{capture_id}/page.html")
def get_capture_html(capture_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    html = get_raw_html(user_id, capture_id)
    if html is None:
        raise HTTPException(404, "No page HTML for this capture")
    return Response(content=html, media_type="text/html; charset=utf-8")


# ─── PATCH /api/capture/{capture_id} ──────────────────────────────
# Update project / tags on a capture

class UpdateRequest(BaseModel):
    project: str | None = None
    tags: list[str] | None = None


@router.patch("/capture/{capture_id}")
def update_capture(
    capture_id: str,
    update: UpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    conn = get_db(user_id)
    try:
        if update.project is not None:
            conn.execute("UPDATE captures SET project=? WHERE id=?", (update.project, capture_id))
        if update.tags is not None:
            conn.execute("UPDATE captures SET tags=? WHERE id=?", (json.dumps(update.tags), capture_id))
        conn.commit()
    finally:
        conn.close()

    updated = get_capture_ref(user_id, capture_id)
    if updated is None:
        raise HTTPException(500, "Failed to read back capture after update")
    return {"success": True, "id": capture_id, "project": updated["project"], "tags": updated["tags"]}


# ─── DELETE /api/capture/{capture_id} ─────────────────────────────

@router.delete("/capture/{capture_id}")
def delete_capture(capture_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    # Delete from DB
    deleted = delete_capture_ref(user_id, capture_id)
    if not deleted:
        raise HTTPException(404, "Capture not found")

    # Delete raw filesystem data (optional — keep for archive?)
    # For now, keep raw files. User can manually clean up.
    return {"success": True, "id": capture_id, "message": "Capture deleted (raw data retained)"}


# ─── POST /api/capture/{capture_id}/reextract ─────────────────────

@router.post("/capture/{capture_id}/reextract")
def reextract_capture(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Pārlaiž Extractor pipeline — dzēš vecos KnowledgeObjects un izvelk no jauna."""
    user_id = current_user["user_id"]
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    raw = load_raw_capture(user_id, capture_id)
    if not raw:
        raise HTTPException(404, "Raw capture data not found")

    # Get raw CapturePackage + HTML
    html = get_raw_html(user_id, capture_id)

    # Delete old knowledge objects
    deleted = delete_knowledge_for_capture(user_id, capture_id)

    # Re-run extractor
    result = extract_and_save(user_id, raw, html=html)

    return {
        "success": True,
        "id": capture_id,
        "deleted": deleted,
        "extracted": len(result.knowledge_objects),
        "message": f"Re-extracted: {len(result.knowledge_objects)} knowledge objects",
        "warnings": result.warnings,
    }


# ─── GET /api/capture ─────────────────────────────────────────────

@router.get("/capture")
def list_all_captures(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    captures = list_captures(user_id)
    return {"captures": captures}


# ─── GET /api/tags ────────────────────────────────────────────────

@router.get("/tags")
def get_tags(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        rows = conn.execute("SELECT project, tags, capture_type FROM captures").fetchall()
        projects = {}
        all_tags = set()
        type_count = {}

        for row in rows:
            ct = row["capture_type"] or "page"
            type_count[ct] = type_count.get(ct, 0) + 1

            p = (row["project"] or "").strip()
            if p:
                projects[p] = projects.get(p, 0) + 1

            for t in (json.loads(row["tags"]) if isinstance(row["tags"], str) else []):
                if t.strip():
                    all_tags.add(t.strip())

        total = conn.execute("SELECT COUNT(*) as c FROM captures").fetchone()["c"] or 0

        return {
            "total_items": total,
            "projects": [{"name": k, "count": v} for k, v in sorted(projects.items())],
            "tags": sorted(all_tags),
            "types": [{"type": k, "count": v} for k, v in sorted(type_count.items())],
        }
    finally:
        conn.close()


# ─── POST /api/projects ───────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    name: str


@router.post("/projects")
def create_project(request: ProjectCreateRequest, current_user: dict = Depends(get_current_user)):
    name = request.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")

    # Projects are just strings on captures — no separate table needed
    # But we can validate it exists in the DB
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        # Ensure at least one capture uses this project
        count = conn.execute("SELECT COUNT(*) as c FROM captures WHERE project=?", (name,)).fetchone()["c"]
        return {"success": True, "name": name, "existing_captures": count}
    finally:
        conn.close()


# ─── POST /api/projects/delete ────────────────────────────────────

class ProjectDeleteRequest(BaseModel):
    name: str


@router.post("/projects/delete")
def delete_project(request: ProjectDeleteRequest, current_user: dict = Depends(get_current_user)):
    name = request.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")
    if name.lower() in ("all items", "uncategorized"):
        raise HTTPException(400, "Cannot delete a built-in filter")

    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        count = conn.execute("SELECT COUNT(*) as c FROM captures WHERE LOWER(project)=LOWER(?)", (name,)).fetchone()["c"] or 0
        conn.execute("UPDATE captures SET project='' WHERE LOWER(project)=LOWER(?)", (name,))
        conn.commit()
        return {"success": True, "message": f"Removed project '{name}' from {count} capture(s)."}
    finally:
        conn.close()


# ─── POST /api/tags/add / delete / rename ────────────────────────

class TagAddRequest(BaseModel):
    tag: str

class TagDeleteRequest(BaseModel):
    tag: str

class TagRenameRequest(BaseModel):
    old: str
    new: str


@router.post("/tags/add")
def add_tag(request: TagAddRequest, current_user: dict = Depends(get_current_user)):
    return {"success": True, "message": f"Tag '{request.tag}' is available."}


@router.post("/tags/delete")
def delete_tag(request: TagDeleteRequest, current_user: dict = Depends(get_current_user)):
    tag = request.tag.strip()
    if not tag:
        raise HTTPException(400, "Tag name is required")
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        rows = conn.execute("SELECT id, tags FROM captures").fetchall()
        count = 0
        for row in rows:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
            if tag in tags:
                conn.execute(
                    "UPDATE captures SET tags=? WHERE id=?",
                    (json.dumps([t for t in tags if t != tag]), row["id"]),
                )
                count += 1
        conn.commit()
        return {"success": True, "message": f"Removed '{tag}' from {count} capture(s)."}
    finally:
        conn.close()


@router.post("/tags/rename")
def rename_tag(request: TagRenameRequest, current_user: dict = Depends(get_current_user)):
    old = request.old.strip()
    new = request.new.strip()
    if not old or not new:
        raise HTTPException(400, "Both old and new tag names required")
    if old == new:
        return {"success": True, "message": "No change needed."}
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        rows = conn.execute("SELECT id, tags FROM captures").fetchall()
        count = 0
        for row in rows:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
            if old in tags:
                conn.execute(
                    "UPDATE captures SET tags=? WHERE id=?",
                    (json.dumps([new if t == old else t for t in tags]), row["id"]),
                )
                count += 1
        conn.commit()
        return {"success": True, "message": f"Renamed '{old}' to '{new}' in {count} capture(s)."}
    finally:
        conn.close()


# ─── GET /api/local/search ────────────────────────────────────────

@router.get("/local/search")
def local_search(q: str = "", current_user: dict = Depends(get_current_user)):
    if not q:
        return []
    user_id = current_user["user_id"]
    results = search_captures(user_id, q)
    # Enhance with type info
    for r in results:
        r["_type"] = "saved"
    return results


# ─── Bookmark import (simplified — no HTMLParser needed for now) ──

@router.post("/import/bookmarks")
def import_bookmarks(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    raise HTTPException(501, "Bookmark import not yet implemented for Capture Package format")