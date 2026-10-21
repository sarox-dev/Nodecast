"""Token-efficient retrieval and ViewModel construction over Atomic Schema v2."""

import hashlib
import json
import re
import uuid
from collections import defaultdict

from app.services.ai_client import AIClientError, call_provider_model, stream_provider_model
from app.services.database import (
    enrich_atomics_with_sources,
    get_ai_assignment_for_feature,
    get_ai_provider,
    get_atomic_by_id,
    get_atomic_relations,
    get_db,
    search_atomics,
)


ERROR_RE = re.compile(r"(?:\b[A-Z][A-Za-z]+Error\b|\b(?:error|exception|traceback|failed)\b|\b[A-Z]{2,8}-?\d{3,}\b)", re.I)
COMPARE_RE = re.compile(r"\b(?:compare|comparison|difference|differences|versus|vs\.?|atšķirīb)\b", re.I)
FEATURE_RECALL_SYNTHESIS = "recall_synthesis"
STREAM_FIELDS = ("VIEW", "TITLE", "SUMMARY", "SECTION", "CONTENT", "EVIDENCE")


def detect_intent(query: str) -> str:
    if ERROR_RE.search(query): return "problem"
    if COMPARE_RE.search(query): return "compare"
    if query.lower().startswith(("source:", "sources ")): return "sources"
    words = query.split()
    return "focus" if 0 < len(words) <= 3 else "list"


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


def _ai_synthesis(user_id: str, query: str, intent: str, evidence: list[dict]) -> dict | None:
    """Create a cited answer from a small, already-retrieved evidence packet.

    Recall has its own assignment: a capture-enrichment model must never become a
    surprise query-time provider call merely because it was configured earlier.
    """
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_RECALL_SYNTHESIS)
    provider = get_ai_provider(user_id, assignment["provider_id"]) if assignment else None
    if not provider or not evidence: return None
    compact = [{"id": a["id"], "type": a.get("type"), "text": (a.get("content") or "")[:650], "source": a.get("source_title") or a.get("source_url")} for a in evidence[:12]]
    prompt = """Answer only from the supplied saved evidence. Return JSON with keys view, title, summary, sections.
view must be list, focus, compare, or problem. sections is an array of {title,content,evidence_ids}.
Every section MUST cite one or more supplied evidence_ids. Do not make claims that lack a citation.
For compare, use shared dimensions as section titles and never invent missing values. For problem, organize exact problem, causes, solutions and outcomes. Keep the answer concise."""
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


def _memory_context(user_id: str, query: str, limit: int, token_budget: int, requested_view: str) -> tuple[dict, list[dict], str]:
    intent = detect_intent(query)
    raw = enrich_atomics_with_sources(user_id, search_atomics(user_id, query, limit=30))
    evidence = [a for a in raw if a.get("role", "evidence") == "evidence" and a.get("status", "ready") != "rejected"]
    evidence = _diverse(evidence, 12)
    cards=[]; packet=[]; used=0
    for atomic in evidence:
        card=_card(atomic)
        if cards and used + card["token_estimate"] > token_budget: break
        cards.append(card); used += card["token_estimate"]
        packet.append(atomic)
        if len(cards) >= max(1,min(limit,8)): break
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
    return {
        "query":{"text":query,"intent":intent}, "view":view, "items":cards,
        "evidence": cards,
        "sources": list(source_groups.values()),
        "answer": None,
        "synthesis_status": "local_only",
        "synthesis": {"status":"local_only","reason":"No Recall synthesis provider is configured."},
        "capabilities":["open","expand","trace_sources","graph"],
        "available_views":["list","focus","sources","compare","problem","graph"],
        "page":{"cursor":None,"has_more":len(evidence)>len(cards)}, "token_estimate":used,
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


def query_memory(user_id: str, query: str, limit: int = 8, token_budget: int = 700, requested_view: str = "auto", synthesize: bool = True) -> dict:
    result, packet, intent = _memory_context(user_id, query, limit, token_budget, requested_view)
    if not synthesize:
        return result
    # The model may cite only evidence the UI can open directly in this packet.
    return _with_synthesis(result, _ai_synthesis(user_id, query, intent, packet), requested_view)


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

    def feed(self, delta: str) -> str:
        self.buffer += delta
        visible = []
        while self.buffer:
            if self.field:
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
                self.buffer = self.buffer[len(matched) + 1:].lstrip()
                if matched in {"SUMMARY", "CONTENT"}:
                    self.field = matched
                elif matched == "SECTION":
                    newline = self.buffer.find("\n")
                    if newline < 0:
                        return "".join(visible)
                    visible.extend(("\n\n", self.buffer[:newline], "\n"))
                    self.buffer = self.buffer[newline + 1:]
                else:
                    newline = self.buffer.find("\n")
                    if newline < 0:
                        return "".join(visible)
                    self.buffer = self.buffer[newline + 1:]
                continue
            if any(name.startswith(upper) for name in STREAM_FIELDS):
                break
            newline = self.buffer.find("\n")
            if newline < 0:
                break
            self.buffer = self.buffer[newline + 1:]
        return "".join(visible)


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
            data["title"] = value[:160]
        elif key == "SUMMARY":
            data["summary"] = value[:1000]
        elif key == "SECTION":
            current = {"title": value[:160], "content": "", "evidence_ids": []}
            data["sections"].append(current)
        elif key == "CONTENT" and current is not None:
            current["content"] = value[:3000]
        elif key == "EVIDENCE" and current is not None:
            current["evidence_ids"] = [item.strip() for item in value.split(",") if item.strip() in valid_ids]
    data["sections"] = [section for section in data["sections"] if section["content"] and section["evidence_ids"]]
    if not data["summary"] or not data["sections"]:
        return None
    data["status"] = "success"
    return data


def stream_memory_query(user_id: str, query: str, limit: int = 8, token_budget: int = 700, requested_view: str = "auto"):
    """Yield JSON-serializable stream events for an evidence-cited recall answer."""
    result, packet, intent = _memory_context(user_id, query, limit, token_budget, requested_view)
    assignment = get_ai_assignment_for_feature(user_id, FEATURE_RECALL_SYNTHESIS)
    provider = get_ai_provider(user_id, assignment["provider_id"]) if assignment else None
    if not provider or not packet:
        yield {"event": "done", "data": result}
        return

    streaming = dict(result)
    streaming["synthesis_status"] = "streaming"
    streaming["synthesis"] = {"status": "streaming", "model": assignment["model"]}
    yield {"event": "meta", "data": streaming}
    compact = [{"id": a["id"], "type": a.get("type"), "text": (a.get("content") or "")[:650], "source": a.get("source_title") or a.get("source_url")} for a in packet[:12]]
    prompt = """Answer only from the supplied saved evidence. Use exactly these one-line fields: VIEW, TITLE, SUMMARY, SECTION, CONTENT, EVIDENCE. Each SECTION must be followed by one CONTENT line and one comma-separated EVIDENCE line containing only supplied evidence IDs. Never use newlines inside values. Every section must cite at least one evidence ID. Keep the answer concise and do not add markdown or other fields."""
    raw, display = [], _StreamingDisplayParser()
    try:
        for delta in stream_provider_model(user_id, provider, assignment["model"], [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"query": query, "intent": intent, "evidence": compact}, ensure_ascii=False)[:12000]},
        ], timeout=45):
            raw.append(delta)
            visible = display.feed(delta)
            if visible:
                yield {"event": "delta", "text": visible}
    except AIClientError as exc:
        failed = _with_synthesis(result, {"status": "error", "code": exc.code, "message": str(exc), "http_status": exc.status_code, "model": assignment["model"]}, requested_view)
        yield {"event": "done", "data": failed}
        return

    synthesis = _parse_streamed_synthesis("".join(raw), {item["id"] for item in packet}, assignment["model"])
    if not synthesis:
        failed = _with_synthesis(result, {"status": "error", "code": "ai_malformed_output", "message": "AI synthesis could not be validated. Local results are still available.", "model": assignment["model"]}, requested_view)
        yield {"event": "done", "data": failed}
        return
    yield {"event": "done", "data": _with_synthesis(result, synthesis, requested_view)}


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
        "page":{"cursor":None,"has_more":len(rows)>len(evidence)},
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
