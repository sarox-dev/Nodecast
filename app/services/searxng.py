import requests
from app.core.config import SEARXNG_URL, TIMEOUT
from app.services.search_cache import search_cache

def search(query: str, page: int = 1, engines: str | None = None, categories: str = "general"):
    cached = search_cache.get(query, engines, page)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "pageno": page,
                "engines": engines,
                "categories": categories,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    results = []

    for item in data.get("results", []):
        engines_value = item.get("engines")
        if isinstance(engines_value, list):
            engines_list = [str(engine).strip() for engine in engines_value if str(engine).strip()]
        else:
            engine_str = item.get("engine", "") or ""
            engines_list = [engine.strip() for engine in engine_str.split(",") if engine.strip()]

        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "thumbnail": item.get("img_src"),
            "engines": engines_list,
        })

    total = data.get("number_of_results", 0)
    response_data = {
        "results": results,
        "total": total,
    }
    search_cache.set(query, engines, page, response_data)
    return response_data