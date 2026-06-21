import requests
from app.core.config import SEARXNG_URL, TIMEOUT

def search(query: str, page: int = 1, count: int = 10, engines: str | None = None, categories: str = "general"):
    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "pageno": page,
                "count": count,
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
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "thumbnail": item.get("img_src"),
        })

    return results