import json
from pathlib import Path

from fastapi import APIRouter, Query
from app.services.searxng import search as searxng_search
from app.services.database import get_db

router = APIRouter()
SEARXNG_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "searxng" / "settings.yml"


def _to_item(row) -> dict:
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


def local_search(q: str, project: str | None = None):
    if not q: return []
    terms = [t for t in q.lower().strip().split() if t]
    if not terms: return []
    pf = (project or "").strip()
    conn = get_db()
    try:
        results = []
        for row in conn.execute("SELECT * FROM items ORDER BY saved_at DESC").fetchall():
            p = (row["project"] or "").strip().lower()
            if pf:
                if pf == "__uncategorized__":
                    tgs = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
                    if p or tgs: continue
                elif p != pf.lower(): continue
            text = " ".join([row["content"] or "", row["source_title"] or "",
                             row["source_site_name"] or "", row["source_url"] or "",
                             row["project"] or ""]).lower()
            try:
                text += " " + " ".join(json.loads(row["tags"]) if isinstance(row["tags"], str) else [])
            except Exception: pass
            if all(t in text for t in terms):
                results.append(_to_item(row))
        return results
    finally:
        conn.close()


@router.get("/search")
def search_route(q: str | None = Query(None), type: str = Query("web"),
                  page: int = Query(1, ge=1), engines: str | None = Query(None),
                  project: str | None = Query(None)):
    if not q: return {"message": "use ?q="}
    if engines is not None: engines = engines.strip() or None
    page1 = page == 1
    saved = local_search(q, project=project) if page1 else []
    if project and page1:
        return {"results": saved, "total": len(saved)}
    web = searxng_search(q, page, engines, "images" if type == "images" else "general") or {}
    wr = web.get("results", [])
    for r in wr: r["_type"] = "web"; r["source"] = "web"
    base = saved if page1 else []
    return {"results": base + wr, "total": len(base) + web.get("total", 0)}


@router.get("/browse")
def browse_captures(project: str | None = Query(None)):
    conn = get_db()
    try:
        pf = (project or "").strip()
        if pf == "__uncategorized__":
            rows = conn.execute("""SELECT * FROM items WHERE (project IS NULL OR project = '')
                AND (tags IS NULL OR tags = '[]') ORDER BY saved_at DESC LIMIT 100""").fetchall()
        elif pf:
            rows = conn.execute("SELECT * FROM items WHERE LOWER(project)=LOWER(?) ORDER BY saved_at DESC LIMIT 100", (pf,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM items ORDER BY saved_at DESC LIMIT 100").fetchall()
        return [_to_item(r) for r in rows]
    finally:
        conn.close()


def _read_engine_list():
    if not SEARXNG_SETTINGS_PATH.exists(): return []
    engines, inside = [], False
    for line in SEARXNG_SETTINGS_PATH.read_text().splitlines():
        s = line.strip()
        if not inside:
            if s == "engines:": inside = True
            continue
        if line and not line.startswith(" ") and not s.startswith("#"): break
        if s.startswith("engine:") and not (v := s.split("engine:", 1)[1].strip()).startswith("#"):
            engines.append(v)
    return engines


@router.get("/search/engines")
def search_engines():
    unique, seen = [], set()
    for e in _read_engine_list():
        if e and e not in seen: seen.add(e); unique.append(e)
        if len(unique) >= 80: break
    return {"engines": unique}
