"""
HTML Cleaner — deterministic, no AI.
Strips scripts/styles/nav/footer/ads/tracking from raw HTML.
Returns clean text with structure preserved.
"""

import re
from html.parser import HTMLParser


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__()
        self._result = []
        self._skip_tag_depth = 0
        self._skip_tags = {"script", "style", "noscript", "iframe", "svg", "form", "nav", "aside", "footer"}
        self._block_tags = {"article", "main", "section", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
                            "pre", "code", "blockquote", "ul", "ol", "li", "img", "figure", "figcaption",
                            "table", "tr", "td", "th", "thead", "tbody", "dl", "dt", "dd", "hr", "br"}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._skip_tags:
            self._skip_tag_depth += 1
            return
        if self._skip_tag_depth > 0:
            return

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._skip_tags:
            if self._skip_tag_depth > 0:
                self._skip_tag_depth -= 1
            return
        if self._skip_tag_depth > 0:
            return

    def handle_data(self, data):
        if self._skip_tag_depth > 0:
            return
        text = data.strip()
        if text:
            self._result.append(text)


def is_ad_content(text: str) -> bool:
    """Simple heuristic to detect ad/marketing content."""
    lower = text.lower()
    ad_keywords = ["advertisement", "sponsored", "promoted", "buy now", "subscribe now",
                   "limited time offer", "click here", "sign up now", "ad block",
                   "ad blocker", "turn off your ad blocker"]
    return any(kw in lower for kw in ad_keywords)


SKIP_CLASS_PATTERNS = re.compile(
    r'(ad|ads|advertisement|sponsor|promoted|sidebar|footer|header|nav|menu|'
    r'social|share|comment-section|related|recommended|newsletter|popup|modal|'
    r'overlay|cookie|consent|banner|tracking|analytics)',
    re.IGNORECASE
)


def clean_html(html: str) -> str:
    """
    Clean raw HTML: remove scripts, styles, nav, footer, ads, tracking.
    Returns clean text with basic structure.
    """
    if not html:
        return ""

    # Remove script, style, noscript, iframe, svg blocks fast via regex
    html = re.sub(r'<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove comments
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Remove elements with ad-related class/id
    html = re.sub(
        r'<(div|section|aside|nav|footer|header)[^>]*(?:class|id)\s*=\s*["\'][^"\']*?(?:ad|sidebar|footer|nav|menu|social|recommended)[^"\']*["\'][^>]*>.*?</\1>',
        '', html, flags=re.DOTALL | re.IGNORECASE,
    )

    # Parse remaining HTML for clean text
    parser = _Cleaner()
    parser.feed(html)
    lines = parser._result

    # Remove lines that look like ads or short noise
    clean = []
    for line in lines:
        if is_ad_content(line):
            continue
        if len(line) < 3:
            continue
        clean.append(line)

    return "\n".join(clean)


def extract_main_content(html: str) -> str:
    """
    Extract likely main content from HTML (article/main focused).
    Falls back to clean_html if no article/main found.
    """
    if not html:
        return ""

    # Try to find <article> or <main> content
    article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL | re.IGNORECASE)

    target = None
    if article_match:
        target = article_match.group(1)
    elif main_match:
        target = main_match.group(1)

    if target:
        return clean_html(target)
    return clean_html(html)