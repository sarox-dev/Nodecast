"""Compatibility endpoints backed exclusively by atomics."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.services.auth import get_current_user
from app.services.database import get_atomics_by_source, get_atomics_by_type, get_capture_ref, get_db

router = APIRouter()


@router.get("/api/capture/{capture_id}/knowledge")
def get_knowledge(capture_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    if not get_capture_ref(user_id, capture_id):
        raise HTTPException(404, "Capture not found")
    atomics = get_atomics_by_source(user_id, capture_id)
    return {"success": True, "capture_id": capture_id, "count": len(atomics), "atomics": atomics}


@router.get("/api/capture/{capture_id}/markdown")
def get_markdown(capture_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    capture = get_capture_ref(user_id, capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")
    lines = [f"# {capture['source_title'] or 'Untitled'}", ""]
    if capture["source_url"]:
        lines.extend([f"Source: {capture['source_url']}", ""])
    for atomic in get_atomics_by_source(user_id, capture_id):
        content = atomic.get("content", "")
        if atomic["type"] == "heading": lines.append(f"## {content}")
        elif atomic["type"] == "code_block": lines.extend(["```", content, "```"])
        elif atomic["type"] == "quote": lines.append(f"> {content}")
        else: lines.append(content)
        lines.append("")
    return Response("\n".join(lines), media_type="text/markdown; charset=utf-8")


@router.get("/api/knowledge/types")
def list_knowledge_types():
    return {"types": ["text", "heading", "fact", "summary", "tag", "entity", "aggregate", "code_block", "quote", "link", "image"]}


@router.get("/api/knowledge/stats")
def knowledge_stats(current_user: dict = Depends(get_current_user)):
    conn = get_db(current_user["user_id"])
    try: return {r["type"]: r["count"] for r in conn.execute("SELECT type,COUNT(*) count FROM atomics GROUP BY type")}
    finally: conn.close()


@router.get("/api/knowledge/type/{type_}")
def get_by_type(type_: str, current_user: dict = Depends(get_current_user)):
    atomics = get_atomics_by_type(current_user["user_id"], type_)
    return {"success": True, "type": type_, "count": len(atomics), "atomics": atomics}
