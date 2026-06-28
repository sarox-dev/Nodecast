import json
import re
from pathlib import Path

from fastapi import APIRouter, Query
from app.services.searxng import search as searxng_search

router = APIRouter()

# Same path as capture.py
CONTENTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contents"


def local_search(q: str):
    """Full-text search over saved JSON captures."""
    if not q or not CONTENTS_DIR.exists():
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
                (data.get("source", {}).get("url", "") or "")
            ).lower()

            if all(t in searchable for t in terms):
                results.append({
                    "_type": "saved",
                    "id": data.get("id"),
                    "title": data.get("source", {}).get("title", ""),
                    "url": data.get("source", {}).get("url", ""),
                    "content": data.get("content", ""),
                    "context": data.get("context", {}),
                    "thumbnail": None,
                    "source": "local",
                    "site_name": data.get("source", {}).get("site_name", ""),
                    "saved_at": data.get("saved_at", ""),
                })
        except Exception:
            pass

    return results


@router.get("/search")
def search_route(
    q: str | None = Query(None),
    type: str = Query("web"),
    page: int = Query(1, ge=1),
    count: int = Query(10, ge=1, le=50),
    engines: str | None = Query(None),
    mode: str = Query("web"),  # "web" or "all" (merged with local)
):
    if not q:
        # If no query and mode=all, show recent captures as browse
        if mode == "all":
            return list_captures()
        return {"message": "use ?q="}

    # Get web results
    categories = "images" if type == "images" else "general"
    web_response = searxng_search(q, page, count, engines, categories)

    web_total = 0
    web_results = []
    if web_response is not None:
        web_results = web_response.get("results", [])
        web_total = web_response.get("total", 0)

    # Tag web results
    for r in web_results:
        r["_type"] = "web"
        r["source"] = "web"

    if mode == "all":
        # Merge: local results first, then web
        local_results = local_search(q)
        # Deduplicate by URL (web won't have a capture_id)
        seen_urls = {r.get("url", "") for r in local_results if r.get("url")}
        web_filtered = [r for r in web_results if r.get("url") not in seen_urls]
        total = len(local_results) + web_total
        return {
            "results": local_results + web_filtered,
            "total": total,
        }

    return {
        "results": web_results,
        "total": web_total,
    }


def list_captures():
    """Return all saved captures for browse mode."""
    if not CONTENTS_DIR.exists():
        return []

    files = sorted(CONTENTS_DIR.glob("*.json"), reverse=True)
    results = []
    for f in files[:100]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            results.append({
                "_type": "saved",
                "id": data.get("id"),
                "title": data.get("source", {}).get("title", ""),
                "url": data.get("source", {}).get("url", ""),
                "content": data.get("content", ""),
                "context": data.get("context", {}),
                "thumbnail": None,
                "source": "local",
                "site_name": data.get("source", {}).get("site_name", ""),
                "saved_at": data.get("saved_at", ""),
            })
        except Exception:
            pass
    return results
