import json
from pathlib import Path

from fastapi import APIRouter, Query, Depends
from app.services.searxng import search as searxng_search
from app.services.database import get_db
from app.services.auth import get_current_user

router = APIRouter()
SEARXNG_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "searxng" / "settings.yml"


def _to_item(row) -> dict:
    tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
    return {
        "_type": "saved",
        "id": row["id"],
        "title": row["source_title"],
        "url": row["source_url"],
        "site_name": row["source_site_name"],
        "capture_type": row["capture_type"],
        "capture_type_icon": f"/static/assets/capture_types/{row['capture_type'] or 'page'}.svg",
        "project": row["project"],
        "tags": tags,
        "summary": row.get("summary") or "",
        "saved_at": row["saved_at"],
        "captured_at": row["captured_at"],
        "raw_path": row["raw_path"],
        "thumbnail": None,
        "source": "local",
    }


def _captures_query(with_summary: bool = False) -> str:
    base = "SELECT c.* FROM captures c"
    if with_summary:
        base = "SELECT c.*, ai.summary FROM captures c LEFT JOIN capture_ai_tags ai ON c.id = ai.capture_id"
    return base


def local_search(q: str, project: str | None = None, user_id: str = ""):
    if not q:
        return []
    terms = [t for t in q.lower().strip().split() if t]
    if not terms:
        return []
    pf = (project or "").strip()
    conn = get_db(user_id)
    try:
        results = []
        query = _captures_query(with_summary=True) + " ORDER BY c.saved_at DESC"
        for row in conn.execute(query).fetchall():
            p = (row["project"] or "").strip().lower()
            if pf:
                if pf == "__uncategorized__":
                    tgs = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
                    if p or tgs:
                        continue
                elif p != pf.lower():
                    continue
            text = " ".join([
                row["source_title"] or "",
                row["source_site_name"] or "",
                row["source_url"] or "",
                row["project"] or "",
                row["summary"] or "",
            ]).lower()
            try:
                text += " " + " ".join(json.loads(row["tags"]) if isinstance(row["tags"], str) else [])
            except Exception:
                pass
            if all(t in text for t in terms):
                results.append(_to_item(row))
        return results
    finally:
        conn.close()


@router.get("/search")
def search_route(
    q: str | None = Query(None),
    type: str = Query("web"),
    page: int = Query(1, ge=1),
    engines: str | None = Query(None),
    project: str | None = Query(None),
    source: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    if not q:
        return {"message": "use ?q="}
    if engines is not None:
        engines = engines.strip() or None
    page1 = page == 1

    # source=local: only local results (Library mode)
    if source == "local":
        saved = local_search(q, project=project, user_id=current_user["user_id"])
        return {"results": saved, "total": len(saved)}

    # source=web: only web results (Web Search mode)
    if source == "web":
        web = searxng_search(q, page, engines, "images" if type == "images" else "general") or {}
        wr = web.get("results", [])
        for r in wr:
            r["_type"] = "web"
            r["source"] = "web"
        return {"results": wr, "total": web.get("total", 0)}

    # Default: merged local + web (backward compat)
    saved = local_search(q, project=project, user_id=current_user["user_id"]) if page1 else []
    if project and page1:
        return {"results": saved, "total": len(saved)}
    web = searxng_search(q, page, engines, "images" if type == "images" else "general") or {}
    wr = web.get("results", [])
    for r in wr:
        r["_type"] = "web"
        r["source"] = "web"
    base = saved if page1 else []
    return {"results": base + wr, "total": len(base) + web.get("total", 0)}


@router.get("/browse")
def browse_captures(
    project: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    conn = get_db(current_user["user_id"])
    try:
        pf = (project or "").strip()
        query = _captures_query(with_summary=True)
        if pf == "__uncategorized__":
            rows = conn.execute(
                query + """ WHERE (c.project IS NULL OR c.project = '')
                   AND (c.tags IS NULL OR c.tags = '[]') ORDER BY c.saved_at DESC LIMIT 100"""
            ).fetchall()
        elif pf:
            rows = conn.execute(
                query + " WHERE LOWER(c.project)=LOWER(?) ORDER BY c.saved_at DESC LIMIT 100",
                (pf,),
            ).fetchall()
        else:
            rows = conn.execute(query + " ORDER BY c.saved_at DESC LIMIT 100").fetchall()
        return [_to_item(r) for r in rows]
    finally:
        conn.close()


def _read_engine_list():
    if not SEARXNG_SETTINGS_PATH.exists():
        return []
    engines, inside = [], False
    for line in SEARXNG_SETTINGS_PATH.read_text().splitlines():
        s = line.strip()
        if not inside:
            if s == "engines:":
                inside = True
            continue
        if line and not line.startswith(" ") and not s.startswith("#"):
            break
        if s.startswith("engine:") and not (v := s.split("engine:", 1)[1].strip()).startswith("#"):
            engines.append(v)
    return engines


@router.get("/search/engines")
def search_engines():
    unique, seen = [], set()
    for e in _read_engine_list():
        if e and e not in seen:
            seen.add(e)
            unique.append(e)
        if len(unique) >= 80:
            break
    return {"engines": unique}