import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.auth import get_member_user
from app.services.database import set_user_setting
from app.services import recall_cache
from app.services.search_filters import SearchFilters, prepare_filter_context
from app.services.saved_search import filter_options, browse_saved, interpret_with_provider
from app.services.agentic_ask import run_bounded_tool_loop
from app.services.topic_views import get_topic_view, refresh_topic_view
from app.services.memory_retrieval import focused_graph, memory_constellation, memory_detail, memory_feedback, memory_sources, query_memory, recent_memory, relation_feedback, stream_memory_query, stream_memory_query_v2

router = APIRouter(prefix="/api", tags=["memory"])

class MemoryQuery(BaseModel):
    query: str = Field(min_length=0,max_length=1000)
    view: str = "auto"
    limit: int = Field(default=8,ge=1,le=8)
    token_budget: int = Field(default=700,ge=100,le=4000)
    synthesize: bool = True
    mode: str = "auto"
    response_language: str = Field(default="auto", max_length=64)
    cross_language: bool = True
    diagnostics: bool = False
    request_id: str | None = Field(default=None, max_length=128)
    stream_version: int = Field(default=1, ge=1, le=2)
    force_refresh: bool = False
    filters: SearchFilters | None = None
    timezone: str = Field(default="UTC", max_length=80)
    interpret_filters: bool = True
    filter_phrases: list[str] = Field(default_factory=list, max_length=8)

class BrowseQuery(MemoryQuery):
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=1000000)


def request_filter_context(body, user_id):
    if any(len(phrase)>200 for phrase in body.filter_phrases):
        raise HTTPException(422, "Invalid filter phrase")
    try:
        options = filter_options(user_id)
        context = prepare_filter_context(body.query, body.filters.model_dump(mode="json") if body.filters else None,
            body.timezone, body.interpret_filters, [row["value"] for row in options["sources"]], body.filter_phrases)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if not body.query.strip() and not any(context["resolved"].values()):
        raise HTTPException(422, "Enter a search term or choose a filter")
    return context


@router.get("/memory/filters")
def library_filter_options(user=Depends(get_member_user)):
    return filter_options(user["user_id"])


@router.post("/memory/filters/interpret")
def interpret_library_filters(body:MemoryQuery, user=Depends(get_member_user)):
    context = request_filter_context(body, user["user_id"])
    if not body.synthesize:
        return {"filters":context["filters"], "filter_phrases":body.filter_phrases, "status":"local"}
    return interpret_with_provider(user["user_id"], body.query, context)


@router.post("/memory/browse")
def browse_library(body:BrowseQuery, user=Depends(get_member_user)):
    context = request_filter_context(body, user["user_id"])
    return browse_saved(user["user_id"], body.query, context, body.limit, body.offset)


class RelationFeedback(BaseModel): action: str
class MemoryFeedback(BaseModel): feedback: str; outcome: str = ""
class TopicRefresh(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    queries: list[str] = Field(min_length=1,max_length=8)
    force: bool = False

class RecallCacheSettings(BaseModel):
    enabled: bool

@router.get("/memory-cache/settings")
def cache_settings(user=Depends(get_member_user)):
    return {"enabled": recall_cache.enabled(user["user_id"])}

@router.put("/memory-cache/settings")
def update_cache_settings(body: RecallCacheSettings, user=Depends(get_member_user)):
    set_user_setting(user["user_id"], "recall_cache_enabled", str(body.enabled).lower())
    return {"enabled": body.enabled}

@router.delete("/memory-cache")
def clear_cache(user=Depends(get_member_user)):
    return {"removed": recall_cache.clear(user["user_id"])}

@router.post("/memory/query")
def search(body:MemoryQuery,user=Depends(get_member_user)):
    if body.view not in {"auto","list","focus","compare","problem","sources","graph"}:
        raise HTTPException(422,"Invalid memory view")
    if body.mode not in {"auto", "fast", "deep"}:
        raise HTTPException(422,"Invalid query mode")
    if body.response_language != "auto" and not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", body.response_language):
        raise HTTPException(422,"Invalid response language")
    context = request_filter_context(body, user["user_id"])
    filter_args = {"filter_context":context} if body.filters is not None or context["recognized"] else {}
    request_id = body.request_id or uuid.uuid4().hex
    result = query_memory(user["user_id"],body.query,body.limit,body.token_budget,body.view,body.synthesize,body.response_language,
                          expand_search=body.cross_language and body.mode != "fast", diagnostics=body.diagnostics, **filter_args)
    result["request_id"] = request_id
    result["mode"] = body.mode
    result["response_language"] = body.response_language
    should_escalate = body.mode == "deep" or (body.mode == "auto" and (result["query_analysis"]["intent"] in {"compare", "research"} or not result["items"]))
    if should_escalate and not any(context["resolved"].values()):
        deep = run_bounded_tool_loop(user["user_id"], body.query)
        result["agentic"] = {"usage": deep["usage"], "evidence_ids": [item["evidence_id"] for item in deep["evidence"]]}
        if body.diagnostics:
            result["agentic"]["tool_trace"] = deep["tool_trace"]
    return result


@router.post("/memory/query/stream")
def search_stream(body:MemoryQuery,user=Depends(get_member_user)):
    if body.view not in {"auto","list","focus","compare","problem","sources","graph"}:
        raise HTTPException(422,"Invalid memory view")

    context = request_filter_context(body, user["user_id"])
    filter_args = {"filter_context":context} if body.filters is not None or context["recognized"] else {}
    def events():
        expand = body.cross_language and body.mode != "fast"
        if body.stream_version == 1 and not body.synthesize:
            result = query_memory(user["user_id"], body.query, body.limit, body.token_budget, body.view, False, body.response_language, diagnostics=body.diagnostics, **filter_args)
            stream = iter([{"event": "done", "data": result}])
        elif body.stream_version == 1:
            stream = stream_memory_query(user["user_id"], body.query, body.limit, body.token_budget, body.view,
                body.response_language, body.force_refresh, expand_search=expand, diagnostics=body.diagnostics, **filter_args)
        else:
            stream = stream_memory_query_v2(user["user_id"], body.query, body.limit, body.token_budget, body.view, body.request_id or "",
                synthesize=body.synthesize, response_language=body.response_language, force_refresh=body.force_refresh,
                diagnostics=body.diagnostics, expand_search=expand, **filter_args)
        for event in stream:
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store, no-transform",
        "Content-Encoding": "identity",
        "X-Accel-Buffering": "no",
        "X-Content-Type-Options": "nosniff",
    })

@router.get("/memory")
def recent(limit:int=Query(8,ge=1,le=8),user=Depends(get_member_user)):
    return recent_memory(user["user_id"],limit)

@router.get("/memory/constellation/overview")
def constellation(limit:int=Query(48,ge=12,le=60),user=Depends(get_member_user)):
    return memory_constellation(user["user_id"],limit)

@router.post("/memory/topics/refresh")
def refresh_topic(body:TopicRefresh,user=Depends(get_member_user)):
    return refresh_topic_view(user["user_id"],body.title,body.queries,body.force)

@router.get("/memory/topics/{topic_id}")
def topic(topic_id:str,user=Depends(get_member_user)):
    try: return get_topic_view(user["user_id"],topic_id)
    except ValueError: raise HTTPException(404,"Topic not found")

@router.get("/memory/{memory_id}")
def detail(memory_id:str,user=Depends(get_member_user)):
    result=memory_detail(user["user_id"],memory_id)
    if not result: raise HTTPException(404,"Memory not found")
    return result

@router.get("/memory/{memory_id}/sources")
def sources(memory_id:str,user=Depends(get_member_user)):
    result=memory_sources(user["user_id"],memory_id)
    if not result: raise HTTPException(404,"Memory not found")
    return {"sources":result}

@router.get("/memory/{memory_id}/evidence")
def evidence(memory_id:str,user=Depends(get_member_user)):
    result=memory_detail(user["user_id"],memory_id)
    if not result: raise HTTPException(404,"Memory not found")
    return {"evidence":result["evidence"]}

@router.get("/memory/{memory_id}/graph")
def graph(memory_id:str,depth:int=Query(1,ge=1,le=2),include_candidates:bool=False,include_structural:bool=False,user=Depends(get_member_user)):
    return focused_graph(user["user_id"],memory_id,depth,include_candidates,include_structural)

@router.post("/relations/{relation_id}/feedback")
def review_relation(relation_id:str,body:RelationFeedback,user=Depends(get_member_user)):
    if body.action not in {"confirm","not_related"}: raise HTTPException(422,"action must be confirm or not_related")
    if not relation_feedback(user["user_id"],relation_id,body.action): raise HTTPException(404,"Relation not found")
    return {"success":True,"status":"accepted" if body.action=="confirm" else "rejected"}

@router.post("/memory/{memory_id}/feedback")
def review_memory(memory_id:str,body:MemoryFeedback,user=Depends(get_member_user)):
    if body.feedback not in {"helpful","not_helpful"}: raise HTTPException(422,"Invalid feedback")
    if not memory_feedback(user["user_id"],memory_id,body.feedback,body.outcome): raise HTTPException(404,"Memory not found")
    return {"success":True}
