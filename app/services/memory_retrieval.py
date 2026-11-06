"""Token-efficient retrieval and ViewModel construction over Atomic Schema v2."""

import hashlib
import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from collections import defaultdict

from app.services.ai_client import AIClientError, call_provider_model, stream_provider_model
from app.services.query_planning import build_query_plan
from app.services.database import (
    enrich_atomics_with_sources,
    get_ai_assignment_for_feature,
    get_ai_provider,
    get_atomic_by_id,
    get_atomic_relations,
    get_db,
    get_user_setting,
    search_atomics,
    search_atomic_embeddings,
)
from app.services.semantic_retrieval import get_embedding_provider, reciprocal_rank_fusion
from app.services import recall_cache
from app.services.ask_search_plan import merge_ranked_results, provider_search_queries


ERROR_RE = re.compile(r"(?:\b[A-Z][A-Za-z]+Error\b|\b(?:error|exception|traceback|failed)\b|\b[A-Z]{2,8}-?\d{3,}\b)", re.I)
COMPARE_RE = re.compile(r"\b(?:compare|comparison|difference|differences|versus|vs\.?|atšķirīb)\b", re.I)
FEATURE_RECALL_SYNTHESIS = "recall_synthesis"
STREAM_FIELDS = ("VIEW", "TITLE", "SUMMARY", "SECTION", "CONTENT", "EVIDENCE", "BLOCK")
logger = logging.getLogger(__name__)


def detect_intent(query: str) -> str:
    planned = build_query_plan(query)["intent"]
    return {"troubleshoot":"problem","lookup":"focus" if 0 < len(query.split()) <= 3 else "list"}.get(planned,planned)


def _summary(atomic: dict) -> tuple[str, bool]:
    props = atomic.get("properties") or {}
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except json.JSONDecodeError:
            props = {}
    if not isinstance(props, dict):
        props = {}
    generated = str(props.get("summary") or "").strip()
    if generated: return generated, True
    text = atomic.get("content") or ""
    return (text[:260] + ("…" if len(text) > 260 else "")), False


def _card(atomic: dict) -> dict:
    summary, is_ai = _summary(atomic)
    title = atomic.get("context_header") or atomic.get("source_title") or summary[:72] or "Saved memory"
    return {
        "id": atomic["id"], "kind": atomic.get("role", "evidence"), "type": atomic.get("type", "text"),
        "title": title, "summary": summary, "synthesis": "ai" if is_ai else "deterministic",
        "match_reason": "Exact or contextual match", "confidence": atomic.get("confidence", 1.0),
        "source_count": 1 if atomic.get("source_id") else 0, "source_id": atomic.get("source_id"),
        "source_url": atomic.get("source_url", ""), "source_title": atomic.get("source_title", ""),
        "source_site_name": atomic.get("source_site_name", ""),
        "excerpt": (atomic.get("content") or "")[:700],
        "excerpt_hash": hashlib.sha256((atomic.get("content") or "").encode("utf-8")).hexdigest() if atomic.get("content") else "",
        "capabilities": ["open", "expand", "trace_sources", "graph"],
        "token_estimate": max(1, len(summary) // 4),
    }


def _diverse(items: list[dict], limit: int) -> list[dict]:
    chosen, per_source = [], defaultdict(int)
    for item in items:
        source = item.get("source_id") or item["id"]
        if per_source[source] >= 2: continue
        chosen.append(item); per_source[source] += 1
        if len(chosen) >= limit: break
    return chosen


def _select_evidence_candidates(items: list[dict], query: str, limit: int) -> list[dict]:
    """Keep diverse sources first, then fill with additional source evidence.

    Standalone community-navigation tokens are weak evidence unless explicitly
    requested. Short factual snippets and exact identifier matches are untouched.
    """
    question = query.casefold()
    def navigation_only(item: dict) -> bool:
        content = str(item.get("content") or "").strip()
        if not content or content.casefold() in question:
            return False
        if re.fullmatch(r"[ru]/[A-Za-z0-9_]{2,32}", content, re.I):
            return True
        props = item.get("properties") or {}
        if isinstance(props, dict) and props.get("structure_kind") == "heading":
            return True
        words = content.split()
        # Concise title-style lines are often navigation headings; keep normal
        # sentences, technical snippets, and explicitly requested titles.
        return (2 <= len(words) <= 6 and len(content) <= 90
                and all(word[:1].isupper() or word.casefold() in {"for", "with", "and", "to", "of", "the"} for word in words)
                and not re.search(r"[.!?=:\d]", content))

    ordered = sorted(items, key=navigation_only)
    selected, per_source, used = [], defaultdict(int), set()
    for per_source_limit in (2, 4):
        for item in ordered:
            ident = item.get("id")
            source = item.get("source_id") or ident
            if ident in used or per_source[source] >= per_source_limit:
                continue
            selected.append(item)
            used.add(ident)
            per_source[source] += 1
            if len(selected) >= limit:
                return selected
    return selected


def _response_language_instruction(query: str, response_language: str = "auto") -> str:
    plan = build_query_plan(query, response_language=response_language)
    language = plan.get("response_language") or "auto"
    if language in {"auto", "und"}:
        return "Write the answer in the language used by the user's query. Keep quoted evidence in its original language."
    return f"Write the answer in BCP-47 language {language}. Keep quoted evidence in its original language."


def _ai_synthesis(user_id: str, query: str, intent: str, evidence: list[dict], response_language: str = "auto") -> dict | None:
    """Create a cited answer from a small, already-retrieved evidence packet.

    Recall has its own assignment: a capture-enrichment model must never become a
    surprise query-time provider call merely because it was configured earlier.
    """
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_RECALL_SYNTHESIS)
    provider = get_ai_provider(user_id, assignment["provider_id"]) if assignment else None
    if not provider or not evidence: return None
    compact = [{"id": a["id"], "type": a.get("type"), "text": (a.get("content") or "")[:650], "source": a.get("source_title") or a.get("source_url")} for a in evidence[:12]]
    prompt = f"""Answer only from the supplied saved evidence. Return JSON with keys view, title, summary, sections.
view must be list, focus, compare, or problem. sections is an array of {{title,content,evidence_ids}}.
Every section MUST cite one or more supplied evidence_ids. Do not make claims that lack a citation.
For compare, use shared dimensions as section titles and never invent missing values. For problem, organize exact problem, causes, solutions and outcomes. Keep the answer concise.
{_response_language_instruction(query, response_language)}"""
    try:
        result = call_provider_model(user_id, provider, assignment["model"], [
            {"role":"system","content":prompt},
            {"role":"user","content":json.dumps({"query":query,"intent":intent,"evidence":compact},ensure_ascii=False)[:12000]},
        ], timeout=45, raise_errors=True)
    except AIClientError as exc:
        return {
            "status":"error", "code":exc.code, "message":str(exc),
            "http_status":exc.status_code, "model":assignment["model"],
        }
    if not result: return None
    try:
        text=result.strip()
        if text.startswith("```"): text=text.split("\n",1)[-1].rsplit("```",1)[0]
        data=json.loads(text)
        if data.get("view") not in {"list","focus","compare","problem"}: return None
        valid={a["id"] for a in evidence}
        sections=[]
        for section in data.get("sections",[]):
            if not isinstance(section, dict): continue
            cited=[i for i in section.get("evidence_ids",[]) if i in valid]
            if not cited: continue
            section["evidence_ids"]=cited
            sections.append(section)
        if not sections:
            return None
        data["sections"] = sections
        data["status"] = "success"
        data["model"]=assignment["model"]
        return data
    except (json.JSONDecodeError, AttributeError, TypeError): return None


def _candidate_search(user_id: str, query: str, limit: int = 30, embedding_identity: tuple[str, str] | None = None):
    lexical = search_atomics(user_id, query, limit=limit)
    if not embedding_identity:
        return lexical, {"lexical": True, "cross_language": False, "semantic_reason": "not_configured"}
    provider = get_embedding_provider(*embedding_identity)
    if not provider:
        return lexical, {"lexical": True, "cross_language": False, "semantic_reason": "provider_unavailable"}
    vectors = provider.embed([query])
    if len(vectors) != 1 or len(vectors[0]) != provider.dimensions:
        return lexical, {"lexical": True, "cross_language": False, "semantic_reason": "invalid_query_embedding"}
    semantic = search_atomic_embeddings(user_id, vectors[0], provider.provider, provider.model, provider.revision, limit=limit)
    return reciprocal_rank_fusion(lexical, semantic, limit), {"lexical": True, "cross_language": True, "semantic_reason": "available"}


def _memory_context(user_id: str, query: str, limit: int, token_budget: int, requested_view: str, embedding_identity: tuple[str, str] | None = None, response_language: str = "auto", alternative_queries: list[str] | None = None, diagnostics: dict | None = None, searched_queries: list[str] | None = None) -> tuple[dict, list[dict], str]:
    query_plan = build_query_plan(query, response_language=response_language)
    intent = {"troubleshoot":"problem","lookup":"focus" if 0 < len(query.split()) <= 3 else "list"}.get(query_plan["intent"],query_plan["intent"])
    if embedding_identity is None:
        configured_provider = get_user_setting(user_id, "multilingual_embedding_provider", "")
        configured_model = get_user_setting(user_id, "multilingual_embedding_model", "")
        embedding_identity = (configured_provider, configured_model) if configured_provider and configured_model else None
    candidates, retrieval_capabilities = _candidate_search(user_id, query, limit=30, embedding_identity=embedding_identity)
    if diagnostics is not None:
        diagnostics["original_candidates"] = len(candidates)
        diagnostics["alternative_candidate_counts"] = []
    if alternative_queries:
        ranked = [candidates]
        for alternative in alternative_queries[:3]:
            try:
                rows, _ = _candidate_search(user_id, alternative, limit=30, embedding_identity=embedding_identity)
                ranked.append(rows)
                if searched_queries is not None:
                    searched_queries.append(alternative)
                if diagnostics is not None:
                    diagnostics["alternative_candidate_counts"].append(len(rows))
            except Exception:
                logger.warning("Alternative recall search failed; preserving local results")
                if diagnostics is not None:
                    diagnostics["alternative_candidate_counts"].append(None)
        candidates = merge_ranked_results(ranked, limit=30)
    if diagnostics is not None:
        diagnostics["merged_candidates"] = len(candidates)
    raw = enrich_atomics_with_sources(user_id, candidates)
    evidence = [a for a in raw if a.get("role", "evidence") == "evidence" and a.get("status", "ready") != "rejected"]
    evidence = _select_evidence_candidates(evidence, query, 12)
    cards=[]; packet=[]; used=0
    for atomic in evidence:
        card=_card(atomic)
        if cards and used + card["token_estimate"] > token_budget: break
        cards.append(card); used += card["token_estimate"]
        packet.append(atomic)
        if len(cards) >= max(1,min(limit,8)): break
    if diagnostics is not None:
        diagnostics["selected_evidence"] = len(packet)
    view = requested_view if requested_view != "auto" else (intent if intent in {"compare","problem","focus"} else "list")
    source_groups={}
    for atomic in packet:
        source_id=atomic.get("source_id") or "derived"
        source_groups.setdefault(source_id, {
            "source_id":source_id,
            "title":atomic.get("source_title") or "Saved evidence",
            "url":atomic.get("source_url", ""),
            "evidence_ids":[],
        })["evidence_ids"].append(atomic["id"])
    empty_reason = None
    if not packet:
        conn = get_db(user_id)
        try:
            has_sources = bool(conn.execute("SELECT 1 FROM captures LIMIT 1").fetchone())
            has_evidence = bool(conn.execute("SELECT 1 FROM atomics WHERE role='evidence' AND source_id IS NOT NULL AND source_id!='' AND status!='rejected' LIMIT 1").fetchone())
        finally:
            conn.close()
        empty_reason = "no_saved_sources" if not has_sources else "no_indexed_evidence" if not has_evidence else "no_matching_evidence"
    return {
        "query":{"text":query,"intent":intent}, "query_analysis":query_plan, "view":view, "items":cards,
        "evidence": cards,
        "sources": list(source_groups.values()),
        "answer": None,
        "synthesis_status": "local_only",
        "synthesis": {"status":"local_only","code":empty_reason or "not_requested"},
        "capabilities":["open","expand","trace_sources","graph"],
        "retrieval":{"capabilities":retrieval_capabilities,"analyzer":"nodecast-unicode-v2"},
        "available_views":["list","focus","sources","compare","problem","graph"],
        # This endpoint returns a bounded evidence packet, not pageable results.
        "page":{"cursor":None,"has_more":False}, "token_estimate":used,
        "result_id":hashlib.sha256(f"{user_id}:{query}".encode()).hexdigest()[:16],
    }, packet, intent


def _with_synthesis(result: dict, synthesis: dict | None, requested_view: str) -> dict:
    response = dict(result)
    status = (synthesis or {}).get("status", "local_only")
    response["synthesis_status"] = status
    response["synthesis"] = synthesis or {"status":"local_only","reason":"No Recall synthesis provider is configured."}
    response["answer"] = synthesis if status == "success" else None
    if status == "success" and requested_view == "auto":
        response["view"] = synthesis.get("view") or response["view"]
    return response


def query_memory(user_id: str, query: str, limit: int = 8, token_budget: int = 700, requested_view: str = "auto", synthesize: bool = True, response_language: str = "auto") -> dict:
    result, packet, intent = _memory_context(user_id, query, limit, token_budget, requested_view, response_language=response_language)
    if not synthesize:
        return result
    if not packet:
        return result
    # The model may cite only evidence the UI can open directly in this packet.
    synthesis = _ai_synthesis(user_id, query, intent, packet, response_language)
    if synthesis is None:
        assignment = get_ai_assignment_for_feature(user_id, FEATURE_RECALL_SYNTHESIS)
        provider = get_ai_provider(user_id, assignment["provider_id"]) if assignment else None
        synthesis = ({"status":"error", "code":"ai_invalid_output", "message":"AI synthesis returned no valid answer. Local results are still available."}
                     if provider else {"status":"local_only", "code":"provider_unavailable"})
    return _with_synthesis(result, synthesis, requested_view)


def memory_constellation(user_id: str, limit: int = 48) -> dict:
    """Return a bounded, calm overview of accepted knowledge and source groups.

    This is a visual projection, not a retrieval index. Evidence remains attached
    to its capture and is represented by one virtual source node rather than by
    hundreds of individual fragments.
    """
    limit = max(12, min(limit, 60))
    conn = get_db(user_id)
    try:
        source_limit = max(8, min(20, limit // 2))
        knowledge_limit = max(4, limit - source_limit)
        source_rows = list(conn.execute(
            """SELECT c.id,c.source_title,c.source_site_name,c.source_url,c.saved_at,
                      COUNT(a.id) AS evidence_count
               FROM captures c
               JOIN atomics a ON a.source_id=c.id AND a.role='evidence' AND a.status!='rejected'
               GROUP BY c.id
               ORDER BY c.saved_at DESC, evidence_count DESC
               LIMIT ?""",
            (source_limit,),
        ))
        knowledge_rows = list(conn.execute(
            """SELECT a.id,a.role,a.type,a.content,a.context_header,a.canonical_key,a.relevance,
                      a.confidence,a.created_at,
                      (SELECT COUNT(DISTINCT evidence.source_id)
                       FROM atomic_relations relation
                       JOIN atomics evidence ON evidence.id = CASE
                           WHEN relation.source_atomic_id=a.id THEN relation.target_atomic_id
                           ELSE relation.source_atomic_id END
                       WHERE (relation.source_atomic_id=a.id OR relation.target_atomic_id=a.id)
                         AND relation.status='accepted' AND relation.method!='structural'
                         AND evidence.source_id IS NOT NULL) AS source_count
               FROM atomics a
               WHERE a.role IN ('concept','aggregate') AND a.status!='rejected'
               ORDER BY source_count DESC, a.relevance DESC, a.created_at DESC
               LIMIT ?""",
            (knowledge_limit,),
        ))

        nodes = []
        source_node_ids = {}
        for row in source_rows:
            node_id = f"source:{row['id']}"
            source_node_ids[row["id"]] = node_id
            label = row["source_title"] or row["source_site_name"] or row["source_url"] or "Saved source"
            nodes.append({
                "id": node_id, "kind": "source", "label": label[:90],
                "subtitle": row["source_site_name"] or "Source",
                "weight": max(1, int(row["evidence_count"] or 1)),
                "source_id": row["id"], "source_url": row["source_url"] or "",
            })

        knowledge_ids = set()
        for row in knowledge_rows:
            knowledge_ids.add(row["id"])
            label = row["canonical_key"] or row["context_header"] or row["content"] or "Untitled"
            nodes.append({
                "id": row["id"], "kind": row["role"], "label": label[:90],
                "subtitle": "Concept" if row["role"] == "concept" else "Memory group",
                "weight": max(1, int(row["source_count"] or 0)),
                "source_count": int(row["source_count"] or 0),
            })

        atomic_rows = list(conn.execute(
            "SELECT id,source_id FROM atomics WHERE status!='rejected'"
        ))
        atomic_to_node = {
            row["id"]: (row["id"] if row["id"] in knowledge_ids else source_node_ids.get(row["source_id"]))
            for row in atomic_rows
        }
        relation_rows = list(conn.execute(
            """SELECT source_atomic_id,target_atomic_id,relation_type,confidence,strength
               FROM atomic_relations
               WHERE status='accepted' AND method!='structural'
                 AND relation_type NOT IN ('precedes','duplicates_within_source')
               ORDER BY confidence DESC, strength DESC
               LIMIT 600"""
        ))
        edge_map = {}
        for row in relation_rows:
            source = atomic_to_node.get(row["source_atomic_id"])
            target = atomic_to_node.get(row["target_atomic_id"])
            if not source or not target or source == target:
                continue
            key = (source, target, row["relation_type"])
            confidence = float(row["confidence"] if row["confidence"] is not None else row["strength"] or 0.5)
            current = edge_map.get(key)
            if current is None or confidence > current["confidence"]:
                edge_map[key] = {
                    "source_id": source, "target_id": target,
                    "relation_type": row["relation_type"], "confidence": confidence,
                }
        return {"nodes": nodes[:limit], "edges": list(edge_map.values()), "limit": limit}
    finally:
        conn.close()


class _StreamingDisplayParser:
    """Expose only human-readable summary/content fields while retaining raw output for validation."""
    def __init__(self):
        self.buffer = ""
        self.field = ""
        self.at_start = False

    def feed(self, delta: str) -> str:
        self.buffer += delta
        visible = []
        while self.buffer:
            if self.field:
                newline = self.buffer.find("\n")
                if self.field not in {"SUMMARY", "CONTENT"}:
                    if newline < 0:
                        break
                    if self.field == "SECTION":
                        visible.extend(("\n\n", self.buffer[:newline].strip(), "\n"))
                    self.buffer = self.buffer[newline + 1:]
                    self.field = ""
                    continue
                if self.at_start:
                    self.buffer = self.buffer.lstrip(' \t')
                    self.at_start = False
                    if not self.buffer:
                        break
                    newline = self.buffer.find("\n")
                if newline < 0:
                    visible.append(self.buffer)
                    self.buffer = ""
                    break
                visible.append(self.buffer[:newline])
                self.buffer = self.buffer[newline + 1:]
                self.field = ""
                continue

            upper = self.buffer.upper()
            matched = next((name for name in STREAM_FIELDS if upper.startswith(f"{name}:")), None)
            if matched:
                self.buffer = self.buffer[len(matched) + 1:]
                self.field = matched
                self.at_start = True
                continue
            if any(name.startswith(upper) for name in STREAM_FIELDS):
                break
            newline = self.buffer.find("\n")
            if newline < 0:
                break
            self.buffer = self.buffer[newline + 1:]
        return "".join(visible)


def _remove_inline_evidence_ids(text: str, valid_ids: set[str]) -> str:
    text = re.sub(r"\[\s*EVIDENCE\s*:[^\]]*\]", "", text, flags=re.I)
    for evidence_id in valid_ids:
        text = text.replace(f"[{evidence_id}]", "")
    return re.sub(r"[ \t]+([,.;:!?])", r"\1", text).strip()


class _InlineEvidenceFilter:
    """Avoid exposing validated evidence IDs even when a marker spans deltas."""
    def __init__(self, valid_ids: set[str]):
        self.markers = tuple(f"[{item}]" for item in valid_ids)
        self.buffer = ""

    def feed(self, text: str, final: bool = False) -> str:
        self.buffer += text
        result = []
        while self.buffer:
            marker = next((item for item in self.markers if self.buffer.startswith(item)), None)
            if marker:
                self.buffer = self.buffer[len(marker):]
            elif self.buffer.upper().startswith("[EVIDENCE:"):
                end = self.buffer.find("]")
                if end >= 0: self.buffer = self.buffer[end + 1:]
                elif final or len(self.buffer) > 256: self.buffer = ""
                else: break
            elif not final and "[EVIDENCE:".startswith(self.buffer.upper()):
                break
            elif not final and any(item.startswith(self.buffer) for item in self.markers):
                break
            else:
                result.append(self.buffer[0])
                self.buffer = self.buffer[1:]
        return "".join(result)


def _inline_citation_parts(text: str, allowed_ids: set[str], known_ids: set[str]) -> list[dict]:
    pattern = re.compile(r"\[\s*(?:EVIDENCE\s*:\s*([^\]]*)|([A-Za-z0-9_-]{12,64}))\s*\]", re.I)
    parts, position = [], 0
    for match in pattern.finditer(text):
        ids = [item.strip() for item in (match.group(1) if match.group(1) is not None else match.group(2)).split(",")]
        if match.group(1) is None and not any(item in known_ids for item in ids):
            continue
        if match.start() > position: parts.append({"text": text[position:match.start()]})
        parts.extend({"evidence_id": item} for item in ids if item in allowed_ids)
        position = match.end()
    if position < len(text): parts.append({"text": text[position:]})
    return parts


def _validated_synthesis_block(value: str, allowed_ids: set[str]) -> dict | None:
    """Accept only bounded, evidence-backed structured content; never model HTML."""
    try:
        block = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(block, dict):
        return None

    def cell(item):
        if not isinstance(item, dict):
            return None
        if item.get("missing") is True:
            return {"missing": True}
        text, ids = item.get("text"), item.get("evidence_ids")
        if not isinstance(text, str) or not text.strip() or len(text) > 600:
            return None
        if not isinstance(ids, list) or not ids or len(ids) > 8 or any(not isinstance(i, str) or i not in allowed_ids for i in ids):
            return None
        return {"parts": [{"text": _remove_inline_evidence_ids(text.strip(), allowed_ids)}] + [{"evidence_id": i} for i in dict.fromkeys(ids)]}

    kind = block.get("type")
    if not isinstance(kind, str):
        return None
    if kind in {"bullets", "numbered"}:
        items = block.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 12:
            return None
        parsed = [cell(item) for item in items]
        return {"type": kind, "items": parsed} if all(parsed) else None
    if kind == "table":
        columns, rows = block.get("columns"), block.get("rows")
        if not isinstance(columns, list) or not 2 <= len(columns) <= 6 or any(not isinstance(c, str) or not c.strip() or len(c) > 120 for c in columns):
            return None
        if not isinstance(rows, list) or not 1 <= len(rows) <= 12 or any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
            return None
        parsed = [[cell(item) for item in row] for row in rows]
        return {"type": kind, "columns": columns, "rows": parsed} if all(all(row) for row in parsed) else None
    return None


class _StreamingBlockParser:
    """Publish only complete, validated blocks after their section's evidence line."""
    def __init__(self, valid_ids: set[str]):
        self.valid_ids = valid_ids
        self.buffer = ""
        self.section = -1
        self.allowed_ids = set()
        self.count = 0
        self.discard_line = False

    def feed(self, delta: str, final: bool = False) -> list[dict]:
        self.buffer += delta
        events = []
        while "\n" in self.buffer or (final and self.buffer):
            line, sep, self.buffer = self.buffer.partition("\n")
            if self.discard_line:
                self.discard_line = False
                continue
            key, separator, value = line.partition(":")
            if not separator:
                continue
            key, value = key.strip().upper(), value.strip()
            if key == "SECTION":
                self.section += 1
                self.allowed_ids = set()
                self.count = 0
            elif key == "EVIDENCE" and self.section >= 0:
                self.allowed_ids = {item.strip() for item in value.split(",") if item.strip() in self.valid_ids}
            elif key == "BLOCK" and self.section >= 0 and self.count < 4 and len(value) <= 20000:
                block = _validated_synthesis_block(value, self.allowed_ids)
                if block:
                    self.count += 1
                    events.append({"section": self.section, "block": block})
        if len(self.buffer) > 21000:
            self.buffer = ""
            self.discard_line = True
        return events


def _parse_streamed_synthesis(raw: str, valid_ids: set[str], model: str) -> dict | None:
    data = {"view": "list", "title": "", "summary": "", "sections": [], "model": model}
    current = None
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key, value = key.strip().upper(), value.strip()
        if key == "VIEW" and value in {"list", "focus", "compare", "problem"}:
            data["view"] = value
        elif key == "TITLE":
            data["title"] = _remove_inline_evidence_ids(value, valid_ids)[:160]
        elif key == "SUMMARY":
            data["summary"] = value[:1000]
        elif key == "SECTION":
            current = {"title": _remove_inline_evidence_ids(value, valid_ids)[:160], "content": "", "evidence_ids": [], "_blocks": []}
            data["sections"].append(current)
        elif key == "CONTENT" and current is not None:
            current["content"] = value[:3000]
        elif key == "EVIDENCE" and current is not None:
            current["evidence_ids"] = [item.strip() for item in value.split(",") if item.strip() in valid_ids]
        elif key == "BLOCK" and current is not None and len(value) <= 20000 and len(current["_blocks"]) < 4:
            current["_blocks"].append(value)
    data["sections"] = [section for section in data["sections"] if section["content"] and section["evidence_ids"]]
    cited = {item for section in data["sections"] for item in section["evidence_ids"]}
    data["summary_parts"] = _inline_citation_parts(data["summary"], cited, valid_ids)
    data["summary"] = _remove_inline_evidence_ids(data["summary"], valid_ids)
    for section in data["sections"]:
        section["blocks"] = [block for value in section.pop("_blocks") if (block := _validated_synthesis_block(value, set(section["evidence_ids"]))) is not None]
        section["content_parts"] = _inline_citation_parts(section["content"], set(section["evidence_ids"]), valid_ids)
        section["content"] = _remove_inline_evidence_ids(section["content"], valid_ids)
    if not data["summary"] or not data["sections"]:
        return None
    data["status"] = "success"
    return data


def stream_memory_query(user_id: str, query: str, limit: int = 8, token_budget: int = 700, requested_view: str = "auto", response_language: str = "auto", force_refresh: bool = False, expand_search: bool = False, diagnostics: bool = False):
    """Yield JSON-serializable stream events for an evidence-cited recall answer."""
    try:
        cache_enabled = recall_cache.enabled(user_id)
        initial_revision = recall_cache.revision(user_id) if cache_enabled else None
    except sqlite3.Error:
        logger.warning("Recall cache unavailable; continuing without cache", exc_info=True)
        cache_enabled, initial_revision = False, None
    trace = {"planner_status": "not_requested", "alternative_queries": 0} if diagnostics else None
    result, packet, intent = _memory_context(user_id, query, limit, token_budget, requested_view, response_language=response_language, diagnostics=trace)
    if trace is not None:
        result["diagnostics"] = trace
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_RECALL_SYNTHESIS)
    provider = get_ai_provider(user_id, assignment["provider_id"]) if assignment else None
    if not provider:
        if trace is not None: trace["planner_status"] = "provider_unavailable"
        yield {"event": "done", "data": (_with_synthesis(result, {"status":"local_only", "code":"provider_unavailable"}, requested_view) if packet else result)}
        return

    if expand_search:
        # Emit local results before asking the configured model for a plan.
        yield {"event": "meta", "data": result}
        try:
            queries = (provider_search_queries(user_id, provider, assignment["model"], query, diagnostics=trace) if trace is not None else provider_search_queries(user_id, provider, assignment["model"], query))
            if trace is not None: trace["alternative_queries"] = max(0, len(queries) - 1)
            if len(queries) > 1:
                performed = []
                result, packet, intent = _memory_context(user_id, query, limit, token_budget, requested_view, response_language=response_language, alternative_queries=queries[1:], diagnostics=trace, searched_queries=performed)
                if trace is not None: result["diagnostics"] = trace
                for search_text in performed:
                    yield {"event": "search.performed", "query": search_text}
        except Exception:
            logger.warning("Recall query expansion failed; using local results")
            if trace is not None: trace["planner_status"] = "provider_error"
    if not packet:
        yield {"event": "done", "data": result}
        return

    key = None
    try:
        if cache_enabled and initial_revision == recall_cache.revision(user_id):
            key = recall_cache.cache_key(query, packet, initial_revision, assignment, provider, requested_view, response_language)
            cached = None if force_refresh else recall_cache.get(user_id, key, initial_revision)
            if cached:
                answer, created_at = cached
                response = _with_synthesis(result, answer, requested_view)
                response["cache"] = {"hit": True, "created_at": created_at, "match": "exact"}
                yield {"event": "done", "data": response}
                return
    except sqlite3.Error:
        logger.warning("Recall cache lookup failed; continuing without cache", exc_info=True)
        key = None

    streaming = dict(result)
    streaming["synthesis_status"] = "streaming"
    streaming["synthesis"] = {"status": "streaming", "model": assignment["model"]}
    yield {"event": "meta", "data": streaming}
    compact = [{"id": a["id"], "type": a.get("type"), "text": (a.get("content") or "")[:650], "source": a.get("source_title") or a.get("source_url")} for a in packet[:12]]
    prompt = f"""Answer only from the supplied saved evidence. Use one-line fields VIEW, TITLE, SUMMARY, SECTION, CONTENT, EVIDENCE and optionally BLOCK. Each SECTION must have one CONTENT line and one comma-separated EVIDENCE line containing only supplied evidence IDs. Place [EVIDENCE: id] immediately after each supported claim in SUMMARY and CONTENT, using only IDs listed for that section in its EVIDENCE field. Never put IDs in TITLE or SECTION. Never use newlines inside values. Every section must cite at least one evidence ID. Keep the answer concise; do not use markdown.
Choose one primary format per section: prose, bullets, numbered list, or a comparison table. Do not repeat a list or table in SUMMARY or CONTENT. SUMMARY should briefly answer the question without enumerating the same items. When useful, especially for comparisons, add a BLOCK line after the section's EVIDENCE. Its value is a single-line JSON object. For a table use type "table", columns as an array of heading strings, and rows as an array of arrays of cell objects. For lists use type "bullets" or "numbered" and items as an array of item objects. Each cell or item object has a text string and evidence_ids array containing actual section EVIDENCE IDs. Use a cell object with missing set to true when evidence does not support a value. CONTENT is only a short fallback if the block cannot be displayed. Never invent facts.
{_response_language_instruction(query, response_language)}"""
    raw, display = [], _StreamingDisplayParser()
    block_parser = _StreamingBlockParser({item["id"] for item in packet})
    inline_filter = _InlineEvidenceFilter({item["id"] for item in packet})
    try:
        for delta in stream_provider_model(user_id, provider, assignment["model"], [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"query": query, "intent": intent, "evidence": compact}, ensure_ascii=False)[:12000]},
        ], timeout=45):
            raw.append(delta)
            visible = inline_filter.feed(display.feed(delta))
            if visible:
                yield {"event": "delta", "text": visible}
            for block_event in block_parser.feed(delta):
                yield {"event": "answer.block", **block_event}
        tail = inline_filter.feed("", final=True)
        if tail:
            yield {"event": "delta", "text": tail}
        for block_event in block_parser.feed("", final=True):
            yield {"event": "answer.block", **block_event}
    except AIClientError as exc:
        failed = _with_synthesis(result, {"status": "error", "code": exc.code, "message": str(exc), "http_status": exc.status_code, "model": assignment["model"]}, requested_view)
        yield {"event": "done", "data": failed}
        return

    synthesis = _parse_streamed_synthesis("".join(raw), {item["id"] for item in packet}, assignment["model"])
    if not synthesis:
        failed = _with_synthesis(result, {"status": "error", "code": "ai_malformed_output", "message": "AI synthesis could not be validated. Local results are still available.", "model": assignment["model"]}, requested_view)
        yield {"event": "done", "data": failed}
        return
    if key:
        try: recall_cache.put(user_id, key, synthesis, initial_revision)
        except sqlite3.Error: logger.warning("Recall cache write failed", exc_info=True)
    response = _with_synthesis(result, synthesis, requested_view)
    response["cache"] = {"hit": False}
    yield {"event": "done", "data": response}


def stream_memory_query_v2(user_id: str, query: str, limit: int = 8, token_budget: int = 700,
                           requested_view: str = "auto", request_id: str = "", cancel_check=None,
                           synthesize: bool = True, response_language: str = "auto", force_refresh: bool = False, diagnostics: bool = False):
    """Translate the stable recall pipeline into a typed, ordered NDJSON contract."""
    request_id = request_id or uuid.uuid4().hex
    seq = 0

    def event(name, data):
        nonlocal seq
        seq += 1
        return {
            "version": "2.0", "request_id": request_id, "seq": seq, "event": name,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "data": data,
        }

    yield event("request.started", {"mode": "auto"})
    plan = build_query_plan(query, response_language=response_language)
    yield event("query.analyzed", {
        "intent": plan["intent"], "query_language": plan["query_language"],
        "response_language": plan["response_language"], "dimensions": plan["dimensions"],
    })
    yield event("search.started", {"sources": ["lexical", "semantic_if_available"]})
    if cancel_check and cancel_check():
        yield event("request.cancelled", {"reason": "client_cancelled"})
        return
    if not synthesize:
        result, _packet, _intent = _memory_context(user_id, query, limit, token_budget, requested_view, response_language=response_language)
        yield event("search.completed", {"count": len(result.get("items", [])), "retrieval": result.get("retrieval", {})})
        yield event("evidence.selected", {"result": result})
        yield event("usage", {"token_estimate": result.get("token_estimate", 0), "budget": token_budget})
        yield event("request.completed", {"result": result})
        return
    legacy = stream_memory_query(user_id, query, limit, token_budget, requested_view, response_language, force_refresh, expand_search=True, diagnostics=diagnostics)
    evidence_emitted = False
    for item in legacy:
        if cancel_check and cancel_check():
            close = getattr(legacy, "close", None)
            if close: close()
            yield event("request.cancelled", {"reason": "client_cancelled"})
            return
        name = item.get("event")
        if name == "meta":
            data = item["data"]
            yield event("search.completed", {"count": len(data.get("items", [])), "retrieval": data.get("retrieval", {})})
            yield event("evidence.selected", {"result": data})
            evidence_emitted = True
        elif name == "delta":
            yield event("answer.delta", {"text": item.get("text", "")})
        elif name == "answer.block":
            yield event("answer.block", {"section": item["section"], "block": item["block"]})
        elif name == "search.performed":
            yield event("search.performed", {"query": item["query"]})
        elif name == "done":
            data = item["data"]
            if not evidence_emitted:
                yield event("search.completed", {"count": len(data.get("items", [])), "retrieval": data.get("retrieval", {})})
                yield event("evidence.selected", {"result": data})
            yield event("usage", {"token_estimate": data.get("token_estimate", 0), "budget": token_budget})
            yield event("request.completed", {"result": data})


def recent_memory(user_id: str, limit: int = 8) -> dict:
    conn=get_db(user_id)
    try:
        rows=[dict(r) for r in conn.execute(
            """WITH ranked AS (
                 SELECT a.*,ROW_NUMBER() OVER (
                   PARTITION BY COALESCE(a.source_id,a.id)
                   ORDER BY a.created_at DESC,a.position ASC
                 ) AS source_rank
                 FROM atomics a WHERE a.role='evidence' AND a.status!='rejected'
               )
               SELECT * FROM ranked WHERE source_rank<=2
               ORDER BY created_at DESC,position ASC LIMIT ?""", (max(1,min(limit*3,24)),)
        )]
    finally: conn.close()
    evidence=_diverse(enrich_atomics_with_sources(user_id,rows),max(1,min(limit,8)))
    return {
        "query":{"text":"","intent":"recent"}, "view":"list",
        "items":[_card(item) for item in evidence],
        "synthesis":{"status":"not_requested"},
        "available_views":["list","focus","sources","graph"],
        "page":{"cursor":None,"has_more":False},
    }


def memory_detail(user_id: str, atomic_id: str) -> dict | None:
    atomic=get_atomic_by_id(user_id,atomic_id)
    if not atomic: return None
    atomic=enrich_atomics_with_sources(user_id,[atomic])[0]
    relations=get_atomic_relations(user_id,atomic_id)
    return {"memory":_card(atomic),"evidence":[atomic],"relations":relations}


def memory_sources(user_id: str, atomic_id: str) -> list[dict]:
    detail=memory_detail(user_id,atomic_id)
    if not detail: return []
    grouped={}
    for evidence in detail["evidence"]:
        sid=evidence.get("source_id") or "derived"
        grouped.setdefault(sid,{"source_id":sid,"title":evidence.get("source_title") or "Derived memory","url":evidence.get("source_url", ""),"evidence":[]})["evidence"].append(evidence)
    return list(grouped.values())


def focused_graph(user_id: str, atomic_id: str, depth: int = 1, include_candidates: bool = False, include_structural: bool = False) -> dict:
    conn=get_db(user_id)
    try:
        ids={atomic_id}; edges=[]; frontier={atomic_id}
        for _ in range(max(1,min(depth,2))):
            if not frontier: break
            ph=','.join('?' for _ in frontier)
            filters=[]
            if not include_candidates: filters.append("status='accepted'")
            else: filters.append("status!='rejected'")
            if not include_structural: filters.append("relation_type!='precedes'")
            where=" AND " + " AND ".join(filters) if filters else ""
            rows=conn.execute(f"SELECT * FROM atomic_relations WHERE (source_atomic_id IN ({ph}) OR target_atomic_id IN ({ph})){where} ORDER BY confidence DESC LIMIT 30",[*frontier,*frontier]).fetchall()
            nxt=set()
            for row in rows:
                d=dict(row); edges.append(d); nxt.update((d["source_atomic_id"],d["target_atomic_id"]))
            nxt-=ids; ids|=nxt; frontier=nxt
        ids=set(list(ids)[:30]); ph=','.join('?' for _ in ids)
        nodes=[_card(a) for a in enrich_atomics_with_sources(user_id,[dict(r) for r in conn.execute(f"SELECT * FROM atomics WHERE id IN ({ph})",list(ids))])]
        edges=[e for e in edges if e["source_atomic_id"] in ids and e["target_atomic_id"] in ids]
        return {"root_id":atomic_id,"nodes":nodes,"edges":edges}
    finally: conn.close()


def relation_feedback(user_id: str, relation_id: str, action: str) -> bool:
    status="accepted" if action=="confirm" else "rejected"
    conn=get_db(user_id)
    try:
        cur=conn.execute("UPDATE atomic_relations SET status=?,method='user',updated_at=datetime('now') WHERE id=?",(status,relation_id)); conn.commit(); return cur.rowcount>0
    finally: conn.close()


def memory_feedback(user_id: str, atomic_id: str, feedback: str, outcome: str = "") -> bool:
    if not get_atomic_by_id(user_id,atomic_id): return False
    conn=get_db(user_id)
    try:
        conn.execute("INSERT INTO memory_feedback VALUES (?,?,?,?,datetime('now'))",(uuid.uuid4().hex[:16],atomic_id,feedback,outcome[:1000])); conn.commit(); return True
    finally: conn.close()
