"""Deterministic full-page structure extraction with raw HTML source spans."""

from __future__ import annotations

import html as html_module
import re

from app.services.text_analysis import analyze_text, language_hint


EXTRACTOR_ID = "nodecast-structured-html"
EXTRACTOR_VERSION = "1"
_MAIN_RE = re.compile(r"<(article|main)\b[^>]*>(.*?)</\1\s*>", re.I | re.S)
_BLOCK_RE = re.compile(r"<(h[1-6]|p|pre|blockquote|li|tr|dt|dd)\b[^>]*>(.*?)</\1\s*>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>", re.S)


def _text(fragment: str) -> str:
    fragment = re.sub(r"<(br|hr)\b[^>]*>", "\n", fragment, flags=re.I)
    return re.sub(r"\s+", " ", html_module.unescape(_TAG_RE.sub(" ", fragment))).strip()


def extract_structured_blocks(raw_html: str, capture_id: str) -> dict:
    if not raw_html:
        return {"status": "saved_not_indexed", "reason": "missing_html", "blocks": []}
    main = _MAIN_RE.search(raw_html)
    region = main.group(2) if main else raw_html
    base = main.start(2) if main else 0
    blocks, heading = [], ""
    for match in _BLOCK_RE.finditer(region):
        tag = match.group(1).lower(); content = _text(match.group(2))
        if tag.startswith("h"):
            heading = content[:300]
        if len(content) < (2 if tag.startswith("h") else 20):
            continue
        kind = "heading" if tag.startswith("h") else "table_row" if tag == "tr" else "code_block" if tag == "pre" else "quote" if tag == "blockquote" else "list_item" if tag == "li" else "question" if tag == "dt" else "answer" if tag == "dd" else "paragraph"
        analysis = analyze_text(content, mode="index"); language, confidence = language_hint(analysis)
        blocks.append({
            "type": "code_block" if kind == "code_block" else "text", "content": content[:4000],
            "context_header": heading if kind != "heading" else content[:300], "position": len(blocks),
            "properties": {"source_span": {"capture_id": capture_id, "start": base + match.start(), "end": base + match.end(),
                            "anchor": f"html:{base + match.start()}-{base + match.end()}"},
                           "heading": heading, "structure_kind": kind, "language": language,
                           "language_confidence": confidence, "scripts": sorted({item.script for item in analysis.scripts}),
                           "extractor": EXTRACTOR_ID, "extractor_version": EXTRACTOR_VERSION},
        })
        if len(blocks) >= 200:
            break
    useful = [block for block in blocks if block["properties"]["structure_kind"] != "heading"]
    if not useful or sum(len(block["content"]) for block in useful) < 80:
        return {"status": "saved_not_indexed", "reason": "insufficient_main_content", "blocks": []}
    return {"status": "indexed", "reason": "", "blocks": blocks}
