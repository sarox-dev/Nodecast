"""
Fact Extraction Service — extract atomic facts from captured content
using an OpenAI-compatible AI provider.

Feature: fact_extraction
Stores results in facts table.
"""
import json
import logging
from uuid import uuid4
from datetime import datetime, timezone

import httpx

from app.services.ai_crypto import decrypt_api_key
from app.services.ai_tagging import _build_context, _call_ai_model, _parse_ai_response
from app.services.database import (
    get_ai_assignment_for_feature,
    get_ai_provider,
    get_db,
)

logger = logging.getLogger(__name__)

FEATURE_FACT_EXTRACTION = "fact_extraction"

FACT_SYSTEM_PROMPT = """You are a knowledge base fact extraction assistant. Given captured web content with priority markers, extract the key atomic facts.

RULES:
- Extract only the MOST important facts (max 5 per capture).
- Each fact must be a single, self-contained statement.
- Focus on: key claims, statistics, definitions, causal relationships, actionable insights.
- Skip: obvious statements, filler content, marketing fluff, navigation text.
- If an entity is explicitly mentioned in the fact, include its name after a colon.

Output ONE fact per line in this EXACT format:
fact: <the fact text>
category: <insight|definition|statistic|claim|example>
entity: <entity name if applicable, otherwise leave empty>
confidence: <0.0-1.0>

Example:
fact: FastAPI uses Pydantic models for automatic request validation
category: definition
entity: FastAPI
confidence: 0.95

fact: The repository has over 80,000 stars on GitHub
category: statistic
entity: 
confidence: 0.9"""


def extract_facts(user_id: str, capture_id: str) -> dict:
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_FACT_EXTRACTION)
    if not assignment:
        return {
            "status": "no_assignment",
            "message": "No AI provider assigned for fact extraction. Go to Settings → AI to configure.",
        }

    provider = get_ai_provider(user_id, assignment["provider_id"])
    if not provider:
        return {"status": "error", "message": "AI provider not found"}

    context, site_name = _build_context(user_id, capture_id)
    if not context:
        return {"status": "skipped", "message": "No content to analyze"}

    api_key = decrypt_api_key(provider.get("api_key_encrypted", ""))
    messages = [
        {"role": "system", "content": FACT_SYSTEM_PROMPT},
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

    parsed = _parse_facts_text(result)
    if not parsed:
        return {"status": "success", "data": {"facts": [], "count": 0}}

    # Delete old facts for this capture before inserting new ones
    from app.services.database import delete_facts_for_capture
    delete_facts_for_capture(user_id, capture_id)

    conn = get_db(user_id)
    try:
        saved = []
        for f in parsed:
            rid = uuid4().hex[:12]
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO facts (id, capture_id, entity_id, fact_text, confidence, category, created_at) VALUES (?,?,?,?,?,?,?)",
                (rid, capture_id, f.get("entity", ""), f["fact"], f.get("confidence", 0.8), f.get("category", ""), now),
            )
            saved.append({"id": rid, "fact_text": f["fact"], "category": f.get("category", ""), "entity": f.get("entity", "")})
        conn.commit()
    finally:
        conn.close()

    return {"status": "success", "data": {"facts": saved, "count": len(saved)}}


def _parse_facts_text(text: str) -> list[dict]:
    if not text:
        return []
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    facts = []
    current = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("fact:"):
            if current.get("fact"):
                facts.append(current)
            current = {"fact": line.split(":", 1)[1].strip(), "category": "", "entity": "", "confidence": 0.8}
        elif lower.startswith("category:"):
            current["category"] = line.split(":", 1)[1].strip()
        elif lower.startswith("entity:"):
            current["entity"] = line.split(":", 1)[1].strip()
        elif lower.startswith("confidence:"):
            try:
                current["confidence"] = float(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
    if current.get("fact"):
        facts.append(current)
    return facts[:5]