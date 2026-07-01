import json
import re
from pathlib import Path

from fastapi import APIRouter, Query
from app.services.searxng import search as searxng_search

router = APIRouter()

# Same path as capture.py
CONTENTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contents"
SEARXNG_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "searxng" / "settings.yml"


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
                    "project": data.get("project", ""),
                    "tags": data.get("tags", []),
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
    engines: str | None = Query(None),
):
    if not q:
        return {"message": "use ?q="}

    if engines is not None:
        engines = engines.strip() or None

    categories = "images" if type == "images" else "general"
    web_response = searxng_search(q, page, engines, categories)

    web_total = 0
    web_results = []
    if web_response is not None:
        web_results = web_response.get("results", [])
        web_total = web_response.get("total", 0)

    for r in web_results:
        r["_type"] = "web"
        r["source"] = "web"

    return {
        "results": web_results,
        "total": web_total,
    }


@router.get("/browse")
def browse_captures():
    return list_captures()


def _read_engine_list():
    if not SEARXNG_SETTINGS_PATH.exists():
        return []

    engines = []
    inside = False
    try:
        with open(SEARXNG_SETTINGS_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not inside:
                    if stripped == "engines:":
                        inside = True
                    continue
                if line and not line.startswith(" ") and not stripped.startswith("#"):
                    # End of engines section once indentation returns to top level
                    break
                if stripped.startswith("engine:"):
                    engine_value = stripped.split("engine:", 1)[1].strip()
                    if engine_value and not engine_value.startswith("#"):
                        engines.append(engine_value)
    except Exception:
        return []
    return engines


@router.get("/search/engines")
def search_engines():
    engines = _read_engine_list()
    unique = []
    seen = set()
    for engine in engines:
        if engine and engine not in seen:
            seen.add(engine)
            unique.append(engine)
            if len(unique) >= 80:
                break
    return {"engines": unique}


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
                "project": data.get("project", ""),
                "tags": data.get("tags", []),
                "context": data.get("context", {}),
                "thumbnail": None,
                "source": "local",
                "site_name": data.get("source", {}).get("site_name", ""),
                "saved_at": data.get("saved_at", ""),
            })
        except Exception:
            pass
    return results
