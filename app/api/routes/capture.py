import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models.capture_package import CapturePackage, CaptureResponse as CPResponse
from app.services.database import (
    get_db,
    get_capture_ref,
    insert_capture_ref,
    list_captures,
    delete_capture_ref,
    search_captures,
    set_capture_save_reason,
    get_user_setting, set_user_setting, add_ai_job, get_db, get_ai_assignment_for_feature, get_ai_provider,
)
from app.services.raw_storage import (
    save_raw_capture,
    load_raw_capture,
    get_raw_html,
    list_raw_captures,
    raw_exists,
    delete_raw_capture,
)
from app.services.ai_batch import add_pending_jobs_on_save
from app.services.database import delete_atomics_by_source
from app.services.auth import get_capture_user, get_member_user

router = APIRouter()


class CaptureReasonUpdate(BaseModel):
    reason: str = ""
    status: str = "confirmed"

class CaptureReasonSettings(BaseModel):
    ai_enabled: bool = False
    review_enabled: bool = True


@router.get("/capture-reason/settings")
def get_reason_settings(current_user: dict = Depends(get_member_user)):
    uid = current_user["user_id"]
    return {"ai_enabled": get_user_setting(uid, "save_reason_ai_enabled", "true") == "true", "review_enabled": get_user_setting(uid, "save_reason_review_enabled", "true") == "true"}


@router.put("/capture-reason/settings")
def update_reason_settings(body: CaptureReasonSettings, current_user: dict = Depends(get_member_user)):
    uid = current_user["user_id"]
    was_enabled = get_user_setting(uid, "save_reason_ai_enabled", "true") == "true"
    if body.ai_enabled and not was_enabled:
        assignment = get_ai_assignment_for_feature(uid, "save_reason_inference")
        if not assignment or not get_ai_provider(uid, assignment["provider_id"]):
            raise HTTPException(422, "Configure a Save reason suggestions provider in AI settings first.")
    set_user_setting(uid, "save_reason_ai_enabled", str(body.ai_enabled).lower())
    set_user_setting(uid, "save_reason_review_enabled", str(body.review_enabled).lower())
    if body.ai_enabled and not was_enabled:
        c = get_db(uid)
        try:
            ids = [row["id"] for row in c.execute("SELECT id FROM captures WHERE save_reason_status='unknown' AND save_reason_inferred_at='' ORDER BY saved_at DESC")]
        finally:
            c.close()
        for capture_id in ids:
            add_ai_job(uid, capture_id, "save_reason_inference")
        if ids:
            from app.services.ai_batch import start_background_batch
            start_background_batch(uid, "save_reason_inference")
    return {"success": True, **body.model_dump()}


@router.get("/capture-reason/review")
def list_reason_review(current_user: dict = Depends(get_member_user)):
    uid = current_user["user_id"]
    if get_user_setting(uid, "save_reason_review_enabled", "true") != "true":
        return {"items": []}
    c = get_db(uid)
    try:
        rows = c.execute("""SELECT id,source_title,source_url,saved_at,save_reason_suggestion,save_reason_category FROM captures
          WHERE save_reason_status='unknown' AND julianday(saved_at)>=julianday('now','-7 days')
          AND save_reason_inferred_at!='' ORDER BY saved_at DESC LIMIT 20""").fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        c.close()


@router.get("/capture-reason/suggestions")
def recent_reason_suggestions(current_user: dict = Depends(get_capture_user)):
    c = get_db(current_user["user_id"])
    try:
        rows = c.execute("""SELECT save_reason, COUNT(*) AS uses FROM captures WHERE save_reason_status='confirmed' AND save_reason!=''
          GROUP BY save_reason ORDER BY uses DESC, MAX(save_reason_updated_at) DESC LIMIT 4""").fetchall()
        return {"suggestions": [row["save_reason"] for row in rows]}
    finally:
        c.close()


# ─── Helper: add Content-Type for JSON responses ──────────────────

from fastapi.responses import JSONResponse, Response


# ─── POST /api/capture ────────────────────────────────────────────

@router.post("/capture", response_model=CPResponse)
def capture_item(
    body: dict,
    current_user: dict = Depends(get_capture_user),
):
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    saved_at = now.isoformat().replace("+00:00", "Z")

    # Extract page_html from body (optional), remove before validation
    page_html = body.pop("page_html", None)
    reason = body.pop("save_reason", "")
    if not isinstance(reason, str) or len(reason) > 500:
        raise HTTPException(422, "Save reason must be text of at most 500 characters")
    reason = reason.strip()

    # Validate as CapturePackage
    try:
        package = CapturePackage(**body)
    except Exception as e:
        raise HTTPException(422, f"Invalid Capture Package: {e}")

    if not package.captured_at:
        package.captured_at = saved_at

    # Save raw capture to filesystem (immutable)
    try:
        raw_path = save_raw_capture(user_id, package, html=page_html)
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(413, str(e))

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
        save_reason=reason,
    )

    has_anchor = bool(package.anchor and package.anchor.selected_text)
    atomic_count = 0

    if page_html:
        add_pending_jobs_on_save(user_id, package.capture_id)
    assignment = get_ai_assignment_for_feature(user_id, "save_reason_inference") if not reason and get_user_setting(user_id, "save_reason_ai_enabled", "true") == "true" else None
    if assignment and get_ai_provider(user_id, assignment["provider_id"]):
        from app.services.ai_batch import start_background_batch
        add_ai_job(user_id, package.capture_id, "save_reason_inference")
        start_background_batch(user_id, "save_reason_inference")

    if has_anchor:
        msg = "Saved with highlight — atomic extraction queued"
    elif page_html:
        msg = "Saved — full-page indexing queued"
    else:
        msg = "Saved, not indexed — no page content was provided"

    return CPResponse(
        success=True,
        id=package.capture_id,
        message=msg,
    )


# ─── GET /api/capture/{capture_id} ────────────────────────────────
# Returns the full CapturePackage (from raw filesystem)

@router.put("/capture/{capture_id}/reason")
def update_capture_reason(capture_id: str, body: CaptureReasonUpdate, current_user: dict = Depends(get_capture_user)):
    reason = body.reason.strip()
    if body.status not in {"confirmed", "unknown", "declined"}:
        raise HTTPException(422, "Invalid reason status")
    if len(reason) > 500 or (body.status == "confirmed") != bool(reason):
        raise HTTPException(422, "A confirmed reason must contain 1–500 characters; other statuses require an empty reason")
    if not set_capture_save_reason(current_user["user_id"], capture_id, reason, body.status):
        raise HTTPException(404, "Capture not found")
    return {"success": True, "reason": reason, "status": body.status}


@router.get("/capture/{capture_id}/reason")
def get_capture_reason(capture_id: str, current_user: dict = Depends(get_member_user)):
    ref = get_capture_ref(current_user["user_id"], capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")
    return {"reason": ref.get("save_reason", ""), "status": ref.get("save_reason_status", "unknown"),
            "suggestion": ref.get("save_reason_suggestion", ""), "category": ref.get("save_reason_category", "")}

@router.get("/capture/{capture_id}")
def get_capture(capture_id: str, current_user: dict = Depends(get_member_user)):
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
        "reason": {"text": ref.get("save_reason", ""), "status": ref.get("save_reason_status", "unknown")},
        "has_html": (Path(ref["raw_path"]) / "page.html").exists(),
    }


# ─── GET /api/capture/{capture_id}/page.html ──────────────────────
# Returns the original page HTML

@router.get("/capture/{capture_id}/page.html")
def get_capture_html(capture_id: str, current_user: dict = Depends(get_member_user)):
    user_id = current_user["user_id"]
    if not get_capture_ref(user_id, capture_id):
        raise HTTPException(404, "Capture not found")
    html = get_raw_html(user_id, capture_id)
    if html is None:
        raise HTTPException(404, "No page HTML for this capture")
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": (
                "sandbox; default-src 'none'; img-src data: http: https:; "
                "style-src 'unsafe-inline'; font-src data: http: https:; "
                "form-action 'none'; base-uri 'none'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


# ─── PATCH /api/capture/{capture_id} ──────────────────────────────
# Update project / tags on a capture

class UpdateRequest(BaseModel):
    project: str | None = None
    tags: list[str] | None = None


@router.patch("/capture/{capture_id}")
def update_capture(
    capture_id: str,
    update: UpdateRequest,
    current_user: dict = Depends(get_member_user),
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
def delete_capture(capture_id: str, current_user: dict = Depends(get_member_user)):
    user_id = current_user["user_id"]
    # Delete from DB
    deleted = delete_capture_ref(user_id, capture_id)
    if not deleted:
        raise HTTPException(404, "Capture not found")

    delete_raw_capture(user_id, capture_id)
    return {"success": True, "id": capture_id, "message": "Capture and raw snapshot deleted"}


# ─── POST /api/capture/{capture_id}/reextract ─────────────────────

@router.post("/capture/{capture_id}/reextract")
def reextract_capture(capture_id: str, current_user: dict = Depends(get_member_user)):
    """Delete derived atomics and enqueue the capture for atomic extraction."""
    user_id = current_user["user_id"]
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    html = get_raw_html(user_id, capture_id)
    if not html:
        raise HTTPException(400, "Capture has no HTML to extract")
    deleted = delete_atomics_by_source(user_id, capture_id)
    add_pending_jobs_on_save(user_id, capture_id)

    return {
        "success": True,
        "id": capture_id,
        "deleted": deleted,
        "status": "queued",
        "message": "Atomic re-extraction queued",
    }


# ─── GET /api/capture ─────────────────────────────────────────────

@router.get("/capture")
def list_all_captures(current_user: dict = Depends(get_member_user)):
    user_id = current_user["user_id"]
    captures = list_captures(user_id)
    return {"captures": captures}


# ─── GET /api/tags ────────────────────────────────────────────────

@router.get("/tags")
def get_tags(current_user: dict = Depends(get_member_user)):
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
def create_project(request: ProjectCreateRequest, current_user: dict = Depends(get_member_user)):
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
def delete_project(request: ProjectDeleteRequest, current_user: dict = Depends(get_member_user)):
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
def add_tag(request: TagAddRequest, current_user: dict = Depends(get_member_user)):
    return {"success": True, "message": f"Tag '{request.tag}' is available."}


@router.post("/tags/delete")
def delete_tag(request: TagDeleteRequest, current_user: dict = Depends(get_member_user)):
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
def rename_tag(request: TagRenameRequest, current_user: dict = Depends(get_member_user)):
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
def local_search(q: str = "", current_user: dict = Depends(get_member_user)):
    if not q:
        return []
    user_id = current_user["user_id"]
    results = search_captures(user_id, q)
    # Enhance with type info
    for r in results:
        r["_type"] = "saved"
    return results
