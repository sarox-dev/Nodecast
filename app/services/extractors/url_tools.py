"""
URL Tools — ģeneriski rīki URL apstrādei.

Funkcijas domēnu noteikšanai, URL pattern matching un ceļu izvilkšanai.
"""

import re
from urllib.parse import parse_qs, urlparse


def match_domain(url: str, domains: list[str]) -> bool:
    """
    Pārbauda vai URL domēns atbilst kādam no saraksta.

    Automātiski ignorē www. prefiksu.

    Args:
        url: Pilns URL
        domains: Saraksts ar domēniem (e.g. ['youtube.com', 'youtu.be'])

    Returns:
        True ja domēns atbilst
    """
    if not url or not domains:
        return False
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        return domain in domains
    except Exception:
        return False


def match_url_pattern(url: str, patterns: list[str]) -> bool:
    """
    Pārbauda vai URL ceļš atbilst kādam no patterniem.

    Patterni var būt:
    - Pilns ceļš: "/watch"
    - Prefix: "/shorts/"
    - Substring: "/comments/" (atrodas jebkurā ceļa daļā)
    - Regex: "r/issues/[0-9]+"

    Args:
        url: Pilns URL
        patterns: Saraksts ar ceļa patterniem

    Returns:
        True ja kāds patterns atbilst
    """
    if not url or not patterns:
        return False
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
    except Exception:
        return False

    for pattern in patterns:
        if pattern.startswith("r/"):
            # Regex pattern
            try:
                if re.search(pattern[2:], path):
                    return True
            except re.error:
                continue
        elif pattern == path:
            return True
        elif path.startswith(pattern):
            return True
        elif pattern in path:  # Substring match — atrodas jebkurā ceļa daļā
            return True

    return False


def extract_video_id(url: str) -> str | None:
    """
    Izvelk video ID no YouTube URL.

    Atbalsta:
    - youtube.com/watch?v=VIDEO_ID
    - youtu.be/VIDEO_ID
    - youtube.com/shorts/VIDEO_ID
    - youtube.com/embed/VIDEO_ID

    Returns:
        Video ID vai None
    """
    if not url:
        return None
    try:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")

        if domain in ("youtu.be",):
            return parsed.path.strip("/").split("/")[0] or None

        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[1].split("/")[0] or None

        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[1].split("/")[0] or None

        qs = parse_qs(parsed.query)
        return qs.get("v", [None])[0]
    except Exception:
        return None
