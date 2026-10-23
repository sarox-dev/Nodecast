"""Validated, language-aware query plans with a deterministic local fallback."""

from __future__ import annotations

import re
from typing import Any

from app.services.text_analysis import analyze_text, language_hint


PLAN_SCHEMA_VERSION = 1
ALLOWED_INTENTS = {"lookup", "compare", "explain", "troubleshoot", "research", "sources"}
ALLOWED_FILTER_FIELDS = {"source_site_name", "source_id", "type", "language", "saved_after", "saved_before"}
ALLOWED_FILTER_OPS = {"eq", "in", "gte", "lte"}
_ERROR_RE = re.compile(r"(?:\b[A-Z][A-Za-z]+Error\b|\b(?:error|exception|traceback|failed)\b|\b[A-Z]{1,8}-?\d{3,}\b)", re.I)
_COMPARE_RE = re.compile(r"\b(?:compare|comparison|difference|differences|versus|vs\.?|atšķirīb\w*|salīdzin\w*)\b", re.I)


def _deterministic_intent(query: str) -> str:
    if _ERROR_RE.search(query):
        return "troubleshoot"
    if _COMPARE_RE.search(query):
        return "compare"
    if query.casefold().startswith(("source:", "sources ")):
        return "sources"
    if len(query.split()) > 12:
        return "research"
    return "lookup"


def _entities(query: str) -> list[str]:
    quoted = re.findall(r'["“”]([^"“”]{1,100})["“”]', query)
    technical = re.findall(r"\b(?:[A-Z][A-Za-z0-9.+_-]{2,}|[A-Za-z]+\.[A-Za-z0-9.+_-]+|[A-Z]{1,8}-?\d{3,})\b", query)
    return list(dict.fromkeys((*quoted, *technical)))[:12]


def validate_query_plan(proposed: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(proposed, dict):
        raise ValueError("query plan must be an object")
    intent = proposed.get("intent")
    if intent not in ALLOWED_INTENTS:
        raise ValueError("invalid query plan intent")
    filters = proposed.get("constraints") or []
    if not isinstance(filters, list) or len(filters) > 8:
        raise ValueError("invalid query plan constraints")
    clean_filters = []
    for item in filters:
        if not isinstance(item, dict) or item.get("field") not in ALLOWED_FILTER_FIELDS or item.get("op") not in ALLOWED_FILTER_OPS:
            raise ValueError("invalid query plan constraint")
        value = item.get("value")
        if not isinstance(value, (str, int, float, list)) or len(str(value)) > 500:
            raise ValueError("invalid query plan constraint value")
        clean_filters.append({"field": item["field"], "op": item["op"], "value": value})
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": proposed.get("source", "model"),
        "intent": intent,
        "query_language": str(proposed.get("query_language") or "und")[:35],
        "response_language": str(proposed.get("response_language") or "auto")[:35],
        "scripts": [str(value)[:30] for value in (proposed.get("scripts") or [])[:8]],
        "entities": [str(value)[:100] for value in (proposed.get("entities") or [])[:12]],
        "dimensions": [str(value)[:100] for value in (proposed.get("dimensions") or [])[:12]],
        "constraints": clean_filters,
        "alternative_queries": [str(value)[:500] for value in (proposed.get("alternative_queries") or [])[:6]],
        "missing_information_policy": "state_gaps",
    }


def build_query_plan(query: str, response_language: str = "auto", proposed: dict[str, Any] | None = None) -> dict[str, Any]:
    if proposed is not None:
        return validate_query_plan(proposed)
    analysis = analyze_text(query, mode="query")
    query_language, confidence = language_hint(analysis)
    return validate_query_plan({
        "source": "deterministic",
        "intent": _deterministic_intent(query),
        "query_language": query_language,
        "response_language": query_language if response_language == "auto" and query_language != "und" else response_language,
        "scripts": list(analysis.script_names),
        "entities": _entities(query),
        "dimensions": [],
        "constraints": [],
        "alternative_queries": [],
        "language_confidence": confidence,
    }) | {"language_confidence": confidence}
