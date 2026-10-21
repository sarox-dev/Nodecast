import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.auth import get_current_user
from app.services.memory_retrieval import focused_graph, memory_constellation, memory_detail, memory_feedback, memory_sources, query_memory, recent_memory, relation_feedback, stream_memory_query

router = APIRouter(prefix="/api", tags=["memory"])

class MemoryQuery(BaseModel):
    query: str = Field(min_length=1,max_length=1000)
    view: str = "auto"
    limit: int = Field(default=8,ge=1,le=8)
    token_budget: int = Field(default=700,ge=100,le=4000)
    synthesize: bool = True

class RelationFeedback(BaseModel): action: str
class MemoryFeedback(BaseModel): feedback: str; outcome: str = ""

@router.post("/memory/query")
def search(body:MemoryQuery,user=Depends(get_current_user)):
    if body.view not in {"auto","list","focus","compare","problem","sources","graph"}:
        raise HTTPException(422,"Invalid memory view")
    return query_memory(user["user_id"],body.query,body.limit,body.token_budget,body.view,body.synthesize)


@router.post("/memory/query/stream")
def search_stream(body:MemoryQuery,user=Depends(get_current_user)):
    if body.view not in {"auto","list","focus","compare","problem","sources","graph"}:
        raise HTTPException(422,"Invalid memory view")

    def events():
        for event in stream_memory_query(user["user_id"], body.query, body.limit, body.token_budget, body.view):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

@router.get("/memory")
def recent(limit:int=Query(8,ge=1,le=8),user=Depends(get_current_user)):
    return recent_memory(user["user_id"],limit)

@router.get("/memory/constellation/overview")
def constellation(limit:int=Query(48,ge=12,le=60),user=Depends(get_current_user)):
    return memory_constellation(user["user_id"],limit)

@router.get("/memory/{memory_id}")
def detail(memory_id:str,user=Depends(get_current_user)):
    result=memory_detail(user["user_id"],memory_id)
    if not result: raise HTTPException(404,"Memory not found")
    return result

@router.get("/memory/{memory_id}/sources")
def sources(memory_id:str,user=Depends(get_current_user)):
    result=memory_sources(user["user_id"],memory_id)
    if not result: raise HTTPException(404,"Memory not found")
    return {"sources":result}

@router.get("/memory/{memory_id}/evidence")
def evidence(memory_id:str,user=Depends(get_current_user)):
    result=memory_detail(user["user_id"],memory_id)
    if not result: raise HTTPException(404,"Memory not found")
    return {"evidence":result["evidence"]}

@router.get("/memory/{memory_id}/graph")
def graph(memory_id:str,depth:int=Query(1,ge=1,le=2),include_candidates:bool=False,include_structural:bool=False,user=Depends(get_current_user)):
    return focused_graph(user["user_id"],memory_id,depth,include_candidates,include_structural)

@router.post("/relations/{relation_id}/feedback")
def review_relation(relation_id:str,body:RelationFeedback,user=Depends(get_current_user)):
    if body.action not in {"confirm","not_related"}: raise HTTPException(422,"action must be confirm or not_related")
    if not relation_feedback(user["user_id"],relation_id,body.action): raise HTTPException(404,"Relation not found")
    return {"success":True,"status":"accepted" if body.action=="confirm" else "rejected"}

@router.post("/memory/{memory_id}/feedback")
def review_memory(memory_id:str,body:MemoryFeedback,user=Depends(get_current_user)):
    if body.feedback not in {"helpful","not_helpful"}: raise HTTPException(422,"Invalid feedback")
    if not memory_feedback(user["user_id"],memory_id,body.feedback,body.outcome): raise HTTPException(404,"Memory not found")
    return {"success":True}
