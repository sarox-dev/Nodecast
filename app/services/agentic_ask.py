"""Bounded read-only retrieval tools for Agentic Ask.

Source text is returned as untrusted data.  It never becomes a tool command or
changes server-side permissions and budgets.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.services.database import (
    enrich_atomics_with_sources, get_capture_ref, get_user_db_path,
    search_atomics, search_captures,
)


MAX_ITERATIONS = 4
MAX_EVIDENCE = 12
MAX_FULL_READS = 2
MAX_SECONDS = 45
MAX_TOOL_LIMIT = 12
MAX_READ_CHARS = 12_000
ALLOWED_TOOLS = {"search_evidence", "search_captures", "read_capture", "get_source_details"}


class ToolValidationError(ValueError):
    pass


@dataclass
class AskBudget:
    started: float
    iterations: int = 0
    evidence: int = 0
    full_reads: int = 0

    def check_time(self):
        if time.monotonic() - self.started > MAX_SECONDS:
            raise TimeoutError("agentic_ask_timeout")


def _page(items: list[dict], cursor: int, limit: int) -> dict:
    cursor = max(0, cursor)
    limit = max(1, min(limit, MAX_TOOL_LIMIT))
    selected = items[cursor:cursor + limit]
    next_cursor = cursor + len(selected) if cursor + len(selected) < len(items) else None
    return {"items": selected, "cursor": next_cursor, "has_more": next_cursor is not None}


def execute_read_tool(user_id: str, name: str, arguments: dict, budget: AskBudget) -> dict:
    budget.check_time()
    if name not in ALLOWED_TOOLS or not isinstance(arguments, dict):
        raise ToolValidationError("unsupported_tool")
    cursor = int(arguments.get("cursor", 0) or 0)
    limit = int(arguments.get("limit", 8) or 8)
    if name == "search_evidence":
        query = str(arguments.get("query", ""))[:1000].strip()
        if not query:
            raise ToolValidationError("query_required")
        rows = enrich_atomics_with_sources(user_id, search_atomics(user_id, query, limit=MAX_EVIDENCE))
        page = _page(rows, cursor, min(limit, MAX_EVIDENCE - budget.evidence))
        budget.evidence += len(page["items"])
        page["items"] = [{
            "evidence_id": row["id"], "capture_id": row.get("source_id"),
            "language": (row.get("properties") or {}).get("language", "und"),
            "original_text": row.get("content", ""),
            "source_title": row.get("source_title", ""), "source_url": row.get("source_url", ""),
            "provenance": (row.get("properties") or {}).get("source_span", {}),
        } for row in page["items"]]
        return page
    if name == "search_captures":
        rows = search_captures(user_id, str(arguments.get("query", ""))[:1000])
        page = _page(rows, cursor, limit)
        page["items"] = [{"capture_id": row["id"], "source_title": row["source_title"],
                          "source_url": row["source_url"], "capture_type": row["capture_type"]}
                         for row in page["items"]]
        return page
    capture_id = str(arguments.get("capture_id", ""))
    capture = get_capture_ref(user_id, capture_id)
    if not capture:
        raise ToolValidationError("capture_not_found")
    if name == "get_source_details":
        return {"capture_id": capture_id, "source_title": capture["source_title"],
                "source_url": capture["source_url"], "source_site_name": capture["source_site_name"],
                "captured_at": capture["captured_at"], "saved_at": capture["saved_at"]}
    if budget.full_reads >= MAX_FULL_READS:
        raise ToolValidationError("full_read_budget_exhausted")
    budget.full_reads += 1
    max_chars = max(1, min(int(arguments.get("max_chars", MAX_READ_CHARS)), MAX_READ_CHARS))
    raw_dir = Path(capture.get("raw_path") or "").resolve()
    user_root = get_user_db_path(user_id).parent.resolve()
    if not raw_dir.is_relative_to(user_root):
        raise ToolValidationError("invalid_raw_path")
    text = ""
    capture_json = raw_dir / "capture.json"
    page_html = raw_dir / "page.html"
    if capture_json.is_file():
        payload = json.loads(capture_json.read_text(encoding="utf-8"))
        text = str(((payload.get("anchor") or {}).get("selected_text")) or "")
    if not text and page_html.is_file():
        text = page_html.read_text(encoding="utf-8", errors="replace")
    start = max(0, int(arguments.get("start", 0) or 0))
    return {"capture_id": capture_id, "start": start, "end": min(len(text), start + max_chars),
            "original_text": text[start:start + max_chars], "truncated": start + max_chars < len(text),
            "untrusted_source_data": True}


def run_bounded_tool_loop(user_id: str, query: str, planner: Callable[[dict], dict] | None = None) -> dict:
    """Run validated tool proposals; no planner means a deterministic one-search deep path."""
    budget = AskBudget(time.monotonic())
    transcript, gathered = [], []
    proposal = {"tool": "search_evidence", "arguments": {"query": query, "limit": MAX_EVIDENCE}}
    while budget.iterations < MAX_ITERATIONS:
        budget.check_time(); budget.iterations += 1
        if planner:
            proposal = planner({"query": query, "tool_results": transcript, "limits": {
                "iterations": MAX_ITERATIONS, "evidence": MAX_EVIDENCE, "full_reads": MAX_FULL_READS}})
        if not proposal or proposal.get("done"):
            break
        result = execute_read_tool(user_id, str(proposal.get("tool", "")), proposal.get("arguments") or {}, budget)
        transcript.append({"tool": proposal["tool"], "result": result})
        if proposal["tool"] == "search_evidence":
            gathered.extend(result["items"])
        if not planner or budget.evidence >= MAX_EVIDENCE:
            break
    return {"evidence": gathered[:MAX_EVIDENCE], "tool_trace": transcript,
            "usage": {"iterations": budget.iterations, "evidence": budget.evidence,
                      "full_reads": budget.full_reads, "elapsed_ms": int((time.monotonic() - budget.started) * 1000)}}
