"""Token-efficient retrieval and ViewModel construction over Atomic Schema v2."""

import hashlib
import json
import re
import uuid
from collections import defaultdict

from app.services.ai_client import AIClientError, call_ai_model
from app.services.ai_crypto import decrypt_api_key
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
    assignment = get_ai_assignment_for_feature(user_id, "atomic_extraction")
    provider = get_ai_provider(user_id, assignment["provider_id"]) if assignment else None
    if not provider or not evidence: return None
    compact = [{"id": a["id"], "type": a.get("type"), "text": (a.get("content") or "")[:650], "source": a.get("source_title") or a.get("source_url")} for a in evidence[:12]]
    prompt = """Use only the supplied saved evidence. Return JSON with keys view, title, summary, sections.
view must be list, focus, compare, or problem. sections is an array of {title,content,evidence_ids}.
For compare, use shared dimensions as section titles and never invent missing values. For problem, organize exact problem, causes, solutions and outcomes. Keep the entire answer concise."""
    try:
        result = call_ai_model(provider["base_url"], decrypt_api_key(provider.get("api_key_encrypted", "")), assignment["model"], [
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
        for section in data.get("sections",[]): section["evidence_ids"]=[i for i in section.get("evidence_ids",[]) if i in valid]
        data["model"]=assignment["model"]
        return data
    except (json.JSONDecodeError, AttributeError, TypeError): return None


def query_memory(user_id: str, query: str, limit: int = 8, token_budget: int = 700, requested_view: str = "auto") -> dict:
    intent = detect_intent(query)
    raw = enrich_atomics_with_sources(user_id, search_atomics(user_id, query, limit=30))
    evidence = [a for a in raw if a.get("role", "evidence") == "evidence" and a.get("status", "ready") != "rejected"]
    evidence = _diverse(evidence, 12)
    synthesis = _ai_synthesis(user_id, query, intent, evidence) if intent in {"compare","problem","focus"} else None
    synthesized_view = synthesis.get("view") if synthesis and synthesis.get("status") != "error" else None
    view = requested_view if requested_view != "auto" else (synthesized_view or (intent if intent in {"compare","problem","focus"} else "list"))
    cards=[]; used=0
    for atomic in evidence:
        card=_card(atomic)
        if cards and used + card["token_estimate"] > token_budget: break
        cards.append(card); used += card["token_estimate"]
        if len(cards) >= max(1,min(limit,8)): break
    return {
        "query":{"text":query,"intent":intent}, "view":view, "items":cards,
        "synthesis": synthesis or {"status":"unavailable","reason":"AI provider unavailable or no synthesis required"},
        "available_views":["list","focus","sources","compare","problem","graph"],
        "page":{"cursor":None,"has_more":len(evidence)>len(cards)}, "token_estimate":used,
        "result_id":hashlib.sha256(f"{user_id}:{query}".encode()).hexdigest()[:16],
    }


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
