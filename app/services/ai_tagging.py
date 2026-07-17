"""
AI Tagging Service — Context Builder + OpenAI-compatible model call.

Builds a priority-ranked text context from KnowledgeObjects and sends
it to the configured AI provider. Stores results in capture_ai_tags.
"""

import json
import logging
import re
from pathlib import Path

import httpx

from app.services.ai_crypto import decrypt_api_key
from app.services.database import (
    get_ai_provider,
    get_ai_assignment_for_feature,
    get_capture_ai_tags,
    upsert_capture_ai_tags,
    get_db,
    get_capture_ref,
)
from app.services.knowledge_store import get_knowledge_for_capture
from app.services.raw_storage import load_raw_capture

logger = logging.getLogger(__name__)

FEATURE_TAGGING = "tagging"
FEATURE_SUMMARY = "summary"

# Token budget: approximate chars (1 token ~ 4 chars for most models)
MAX_CHARS = 8000  # ~2000 tokens

BASE_TAGGING_PROMPT = """You are a knowledge base tagging assistant. Given captured web content with priority markers, generate tags as plain text.

IMPORTANT RULES:
- Reuse existing tags from the list below when they fit well, but create new specific tags when needed.
- Do NOT add the website/source name as a tag (e.g., reddit, medium, youtube, wikipedia, quora).
- Use consistent format: lowercase, hyphen-separated (e.g., public-speaking not "public speaking").
- Aim for 3-5 tags. Be specific — prefer meaningful content tags over generic ones.
- Output ONLY tags separated by commas, nothing else. NO markdown fences, NO JSON, NO extra text.
- Example: tag1, tag2, tag3

Existing tags available for reuse (use them when applicable, but don't limit yourself):
{existing_tags_list}"""

BASE_SUMMARY_PROMPT = """You are a knowledge base summarisation assistant. Given captured web content with priority markers, generate a concise summary as plain text.

IMPORTANT RULES:
- Output ONLY one line, nothing else.
- NO markdown fences, NO JSON, NO extra text.
- Line should start with SUMMARY: followed by ONE sentence (max 20 words) capturing the core topic.
- Example:
SUMMARY: This article explains how to set up a CI/CD pipeline with GitHub Actions."""


# ─── Existing tags ──────────────────────────────────────────────────


def _get_existing_tags(user_id: str) -> list[str]:
    """Collect all unique tags from both AI tags and manual tags across all captures."""
    conn = get_db(user_id)
    try:
        all_tags: set[str] = set()

        # Get tags from capture_ai_tags
        rows = conn.execute("SELECT tags FROM capture_ai_tags").fetchall()
        for row in rows:
            try:
                tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
                for t in tags:
                    normalized = _normalize_single_tag(t)
                    if normalized:
                        all_tags.add(normalized)
            except Exception:
                pass

        # Also get manual tags from captures table
        rows2 = conn.execute("SELECT tags FROM captures WHERE tags IS NOT NULL").fetchall()
        for row in rows2:
            try:
                tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else []
                for t in tags:
                    if isinstance(t, str) and t.strip():
                        normalized = _normalize_single_tag(t)
                        if normalized:
                            all_tags.add(normalized)
            except Exception:
                pass

        return sorted(all_tags)
    finally:
        conn.close()


def _build_system_prompt(user_id: str) -> str:
    """Build the taggging system prompt with current existing tags."""
    existing = _get_existing_tags(user_id)
    if existing:
        tags_str = ", ".join(existing)
    else:
        tags_str = "(none yet — create initial tags)"
    return BASE_TAGGING_PROMPT.replace("{existing_tags_list}", tags_str)


def _build_summary_prompt() -> str:
    """Build the summary system prompt (no dynamic tags needed)."""
    return BASE_SUMMARY_PROMPT


# ─── Tag normalization ──────────────────────────────────────────────


def _normalize_single_tag(tag: str) -> str:
    """Normalize a single tag: lowercase, replace spaces with hyphens, strip."""
    t = tag.strip().lower()
    # Replace underscores and spaces with hyphens
    t = re.sub(r'[_\s]+', '-', t)
    # Remove any non-alphanumeric chars except hyphens
    t = re.sub(r'[^a-z0-9\-]', '', t)
    # Remove leading/trailing hyphens
    t = t.strip('-')
    return t


def _normalize_tags(tags: list[str], site_name: str = "") -> list[str]:
    """Normalize and deduplicate tags. Optionally filter out site name."""
    normalized = []
    seen = set()
    site_lower = site_name.strip().lower() if site_name else ""

    for tag in tags:
        t = _normalize_single_tag(tag)
        if not t:
            continue
        # Filter out site name as tag
        if site_lower and t == site_lower:
            continue
        # Filter out very generic single-word sites
        if t in ('reddit', 'medium', 'youtube', 'wikipedia', 'quora', 'github', 'twitter', 'facebook', 'instagram', 'linkedin'):
            continue
        if t not in seen:
            seen.add(t)
            normalized.append(t)

    return normalized


# ─── Context Builder ────────────────────────────────────────────────


def _build_context(user_id: str, capture_id: str) -> tuple[str | None, str]:
    """Build a priority-ranked text context from KnowledgeObjects.

    Returns (context_text, site_name) so caller can use site_name for filtering.
    """
    ref = get_capture_ref(user_id, capture_id)
    if not ref:
        return None, ""

    raw = load_raw_capture(user_id, capture_id)
    if not raw:
        return None, ""

    site_name = (raw.source.site_name or "") if raw.source else ""

    parts: list[str] = []
    chars_used = 0

    def add(priority: int, label: str, text: str):
        nonlocal chars_used
        if not text or not text.strip():
            return
        text = text.strip()
        if chars_used + len(text) > MAX_CHARS:
            remaining = MAX_CHARS - chars_used
            if remaining > 50:
                parts.append(f"[PRIORITY {priority} — {label} (truncated)]\n{text[:remaining]}\n[END]")
            return
        parts.append(f"[PRIORITY {priority} — {label}]\n{text}\n[END]")
        chars_used += len(text)

    # Priority 1: Anchor text (user selection)
    if raw.anchor and raw.anchor.selected_text:
        add(1, "USER SELECTION", raw.anchor.selected_text)
        if raw.anchor.before_text:
            add(1, "BEFORE SELECTION", raw.anchor.before_text)
        if raw.anchor.after_text:
            add(1, "AFTER SELECTION", raw.anchor.after_text)

    # Priority 2: Page metadata
    meta_parts = []
    if raw.source and raw.source.title:
        meta_parts.append(f"Title: {raw.source.title}")
    if raw.source and raw.source.site_name:
        meta_parts.append(f"Site: {raw.source.site_name} (DO NOT use this as a tag)")
    if raw.source and raw.source.url:
        meta_parts.append(f"URL: {raw.source.url}")
    if raw.page_metadata:
        if raw.page_metadata.open_graph:
            og = raw.page_metadata.open_graph
            if og.get("description"):
                meta_parts.append(f"Description: {og['description']}")
    if meta_parts:
        add(2, "PAGE INFO", "\n".join(meta_parts))

    # Priority 3: Structured KnowledgeObjects (extractor output)
    kobs = get_knowledge_for_capture(user_id, capture_id)
    if kobs:
        struct_lines = []
        for ko in kobs:
            if ko.type == "video":
                props = ko.properties or {}
                struct_lines.append(f"[VIDEO] Title: {props.get('title', '')} | Channel: {props.get('author', '')} | Views: {props.get('view_count', '')} | Duration: {props.get('duration', '')}")
                desc = (props.get("description") or "")[:300]
                if desc:
                    struct_lines.append(f"  Description: {desc}")
            elif ko.type == "reddit_post":
                props = ko.properties or {}
                struct_lines.append(f"[REDDIT] Title: {props.get('title', '')} | Subreddit: {props.get('subreddit', '')} | Author: {props.get('author', '')} | Score: {props.get('score', '')}")
                desc = (props.get("description") or "")[:300]
                if desc:
                    struct_lines.append(f"  Content: {desc}")
            elif ko.type == "json_ld":
                props = ko.properties or {}
                struct_lines.append(f"[JSON-LD] Type: {props.get('schema_type', '')} | Keys: {', '.join(list(props.keys())[:5])}")
            elif ko.type == "document":
                props = ko.properties or {}
                blocks = props.get("blocks", [])
                if blocks:
                    doc_text = _format_document_blocks(blocks, budget=MAX_CHARS - chars_used)
                    if doc_text:
                        struct_lines.append(f"[DOCUMENT CONTENT]\n{doc_text}")
            elif ko.type == "anchor":
                continue
            elif ko.type == "metadata":
                continue
            else:
                props = ko.properties or {}
                head = json.dumps(props, ensure_ascii=False)[:200]
                struct_lines.append(f"[{ko.type.upper()}] {head}")
        if struct_lines:
            add(3, "STRUCTURED CONTENT", "\n".join(struct_lines))

    if not parts:
        return None, site_name

    return "\n\n".join(parts), site_name


def _format_document_blocks(blocks: list[dict], budget: int) -> str:
    """Format document blocks as text, respecting a char budget."""
    lines = []
    chars = 0
    for block in blocks:
        block_type = block.get("type", "paragraph")
        text = block.get("text", "") or ""
        alt_text = block.get("alt", "") or ""
        if not text and not alt_text:
            continue
        content = alt_text or text
        if block_type == "heading":
            line = f"[HEADING] {content}"
        elif block_type == "code":
            line = f"[CODE]\n{content}\n[/CODE]"
        elif block_type == "blockquote":
            line = f"[QUOTE] {content}"
        elif block_type == "image":
            line = f"[IMAGE] {alt_text or 'image'}"
        else:
            line = content
        if chars + len(line) > budget:
            break
        lines.append(line)
        chars += len(line)
    return "\n".join(lines)


# ─── AI Call ────────────────────────────────────────────────────────


def _call_ai_model(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    timeout: int = 120,
) -> str | None:
    """Call an OpenAI-compatible chat completion endpoint.
    Returns raw text response (not JSON) for easier parsing with small models."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 500,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            # Some models put response in "reasoning_content" when "content" is empty
            if not content.strip():
                reasoning = data["choices"][0]["message"].get("reasoning_content", "") or ""
                if reasoning.strip():
                    logger.info("AI %s: content empty, using reasoning_content (%d chars)", model, len(reasoning))
                    content = reasoning
                else:
                    logger.warning("AI %s: both content AND reasoning_content empty" , model)
            # LM Studio sometimes returns function-call format {"name": "...", "parameters": {"text": "..."}}
            # when the model was trained for tool use. Extract the actual text from parameters.
            if content.strip().startswith("{"):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "name" in parsed and "parameters" in parsed:
                        params = parsed["parameters"]
                        if isinstance(params, dict):
                            extracted = params.get("text") or params.get("summary") or params.get("tags") or ""
                            if isinstance(extracted, str) and extracted.strip():
                                logger.info("AI %s: extracted text from function-call format (%d chars)", model, len(extracted))
                                content = extracted
                            elif isinstance(extracted, list):
                                content = ", ".join(str(x) for x in extracted)
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
            preview = content.strip()[:150].replace("\n", " ")
            logger.info("AI %s: raw response (%d chars): %s...", model, len(content), preview)
            return _clean_response(content)
    except httpx.ConnectError:
        logger.error("AI %s: Connection refused to %s", model, base_url)
        return None
    except httpx.TimeoutException:
        logger.error("AI %s: Timeout (>%ss) at %s", model, timeout, base_url)
        return None
    except Exception as e:
        logger.error("AI %s: Error: %s", model, e)
        return None


def _clean_response(text: str) -> str:
    """Strip markdown fences and whitespace from AI response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text

def _parse_tags_text(text: str) -> list[str]:
    """Parse tags from plain text response.
    Handles: comma-separated, one-per-line, with/without "Tags:" prefix.
    Filters out model-thinking noise (items that look like reasoning, not tags)."""
    if not text:
        return []
    text = _clean_response(text)
    # Remove common prefixes
    for prefix in ["tags:", "tags:", "tag:", "tag:"]:
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
            break
    # Try newline-separated first (each line = one tag)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) > 1:
        tags = [l.rstrip(".;,").strip().lower() for l in lines]
    else:
        # Comma-separated
        tags = [t.strip().lower().rstrip(".;,") for t in text.split(",") if t.strip()]

    # Filter out noise: tags should be short (< 50 chars), not contain spaces (hyphenated),
    # and not be numbered steps or full sentences
    clean = []
    for t in tags:
        t = t.strip()
        if not t or len(t) < 2:
            continue
        # Skip numbered items like "1-analyze..." or "2-identify..." or "1. analyze"
        if t[0].isdigit() and (t[1:2] in (".-", "-", ".") or len(t) > 40):
            continue
        # Skip very long items (model thinking, not tags)
        if len(t) > 40:
            continue
        # Skip items containing multiple words (sentences, not tags)
        if " " in t and len(t) > 25:
            continue
        # Skip items with common reasoning words/phrases
        reasoning_words = ["the-", "this-", "that-", "they-", "here-", "must-", "should-", "need-",
                          "core-", "very-", "highly-", "extremely", "specific", "relates", "excellent"]
        has_reasoning = any(t.startswith(w) for w in reasoning_words) or \
                        any(w in t for w in ["user-", "describe", "method", "implement", "solution", "approach"])
        if has_reasoning:
            continue
        clean.append(t)

    return clean[:10]  # Max 10 tags


def _parse_summary_text(text: str) -> str:
    """Parse summary text response.
    Expected: SUMMARY: One sentence here.
    Returns just the summary text (empty string if not found)."""
    text = _clean_response(text)
    upper = text.upper()
    if "SUMMARY:" in upper:
        idx = upper.index("SUMMARY:") + 8
        return text[idx:].strip()
    # No prefix found — use the first non-empty line
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return lines[0] if lines else ""


def _parse_ai_response(content: str) -> dict | None:
    """Parse AI response, handling potential JSON in markdown fences.
    Returns any valid JSON dict — callers use .get() for expected keys."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return None
    except json.JSONDecodeError:
        # Try to find any JSON object in the text
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


# ─── Main API ───────────────────────────────────────────────────────


def tag_capture(user_id: str, capture_id: str) -> dict:
    """Tag a single capture using the configured AI provider.

    Returns dict with status: 'success', 'skipped', 'error', 'no_assignment'.
    """
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_TAGGING)
    if not assignment:
        return {"status": "no_assignment", "message": "No AI provider assigned for tagging. Go to Settings → AI to configure."}

    provider = get_ai_provider(user_id, assignment["provider_id"])
    if not provider:
        return {"status": "error", "message": "AI provider not found"}

    # Build context (includes site_name for post-processing)
    context, site_name = _build_context(user_id, capture_id)
    if not context:
        return {"status": "skipped", "message": "No content to analyze"}

    # Build dynamic system prompt with existing tags
    system_prompt = _build_system_prompt(user_id)

    # Decrypt API key
    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))

    # Call AI
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]
    result = _call_ai_model(
        base_url=provider["base_url"],
        api_key=api_key,
        model=assignment["model"],
        messages=messages,
    )

    if not result:
        return {"status": "error", "message": "AI model returned no valid response"}

    # Post-process tags: normalize + filter site names
    raw_tags = _parse_tags_text(result)
    normalized_tags = _normalize_tags(raw_tags, site_name=site_name)

    # Preserve any existing summary/key_concepts from previous runs
    existing_tags = get_capture_ai_tags(user_id, capture_id)
    existing_summary = ""
    existing_concepts = []
    existing_source = []
    if existing_tags:
        existing_summary = existing_tags.get("summary", "")
        existing_concepts = existing_tags.get("key_concepts", [])
        existing_source = existing_tags.get("ai_tags_source", [])

    source_tags = [f"ai:{assignment['model']}"]
    saved = upsert_capture_ai_tags(
        user_id=user_id,
        capture_id=capture_id,
        tags=normalized_tags,
        summary=existing_summary,
        key_concepts=existing_concepts,
        model=assignment["model"],
        ai_tags_source=source_tags,
    )

    return {"status": "success", "data": saved}


def summarize_capture(user_id: str, capture_id: str) -> dict:
    """Summarize a single capture using the configured AI provider.

    Returns dict with status: 'success', 'skipped', 'error', 'no_assignment'.
    """
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_SUMMARY)
    if not assignment:
        return {"status": "no_assignment", "message": "No AI provider assigned for summary. Go to Settings → AI to configure."}

    provider = get_ai_provider(user_id, assignment["provider_id"])
    if not provider:
        return {"status": "error", "message": "AI provider not found"}

    # Build context (same context builder)
    context, site_name = _build_context(user_id, capture_id)
    if not context:
        return {"status": "skipped", "message": "No content to analyze"}

    # Build system prompt
    system_prompt = _build_summary_prompt()

    # Decrypt API key
    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))

    # Call AI
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]
    result = _call_ai_model(
        base_url=provider["base_url"],
        api_key=api_key,
        model=assignment["model"],
        messages=messages,
    )

    if not result:
        return {"status": "error", "message": "AI model returned no valid response"}

    # Parse summary text (plain text format, not JSON)
    existing_summary = _parse_summary_text(result)
    existing_concepts = []

    # Get existing AI tags for this capture to preserve any existing tags
    from app.services.database import get_capture_ai_tags
    existing = get_capture_ai_tags(user_id, capture_id)
    existing_tags = []
    if existing:
        try:
            existing_tags = json.loads(existing["tags"]) if isinstance(existing["tags"], str) else existing.get("tags", [])
        except Exception:
            existing_tags = []

    source_tags = [f"ai:{assignment['model']}"]
    saved = upsert_capture_ai_tags(
        user_id=user_id,
        capture_id=capture_id,
        tags=existing_tags,  # preserve existing tags
        summary=existing_summary,
        key_concepts=existing_concepts,
        model=assignment["model"],
        ai_tags_source=source_tags,
    )

    return {"status": "success", "data": saved}


def get_available_features() -> list[dict]:
    return [
        {"id": FEATURE_TAGGING, "name": "Tag Captures", "description": "Automatically generate tags for saved captures."},
        {"id": FEATURE_SUMMARY, "name": "Generate Summary", "description": "Generate a one-sentence summary of the capture."},
        {"id": "entity_extraction", "name": "Extract Entities", "description": "Extract named entities (tools, people, concepts, etc.) from captures."},
    ]