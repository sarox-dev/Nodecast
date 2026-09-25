"""AI provider configuration and atomic-pipeline controls."""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.ai_crypto import decrypt_api_key, normalize_url_for_docker
from app.services.auth import get_current_user
from app.services.ai_batch import get_batch_status, start_background_batch
from app.services.database import (
    count_pending_ai_jobs, create_ai_provider, delete_ai_assignment, delete_ai_provider,
    get_ai_provider, get_atomic_graph, get_user_setting, list_ai_assignments,
    list_ai_providers, list_captures_without_ai_data, set_ai_assignment,
    set_user_setting, update_ai_provider, add_ai_job,
)

router = APIRouter(prefix="/api/ai")


class ProviderCreate(BaseModel):
    name: str; base_url: str; api_key: str = ""; provider_type: str = "openai_compatible"; provider_key: str = ""; api_style: str = "openai"
class ProviderUpdate(BaseModel):
    name: str | None = None; base_url: str | None = None; api_key: str | None = None; default_model: str | None = None
class AssignmentSet(BaseModel):
    feature: str; provider_id: str; model: str


PROVIDER_PRESETS = [
    {"key":"openai","name":"OpenAI","default_base_url":"https://api.openai.com/v1","requires_api_key":True,"api_style":"openai"},
    {"key":"openrouter","name":"OpenRouter","default_base_url":"https://openrouter.ai/api/v1","requires_api_key":True,"api_style":"openai"},
    {"key":"anthropic","name":"Anthropic","default_base_url":"https://api.anthropic.com/v1","requires_api_key":True,"api_style":"anthropic"},
    {"key":"gemini","name":"Google Gemini","default_base_url":"https://generativelanguage.googleapis.com/v1beta","requires_api_key":True,"api_style":"gemini"},
    {"key":"lmstudio","name":"LM Studio","default_base_url":"http://host.docker.internal:1234/v1","requires_api_key":False,"api_style":"openai"},
    {"key":"ollama","name":"Ollama","default_base_url":"http://host.docker.internal:11434/v1","requires_api_key":False,"api_style":"openai"},
    {"key":"custom","name":"Custom OpenAI Compatible","default_base_url":"","requires_api_key":False,"api_style":"openai"},
]


@router.get("/provider-presets")
def presets(): return {"presets": PROVIDER_PRESETS}

@router.post("/providers/test-connection")
def test_connection(body: ProviderCreate):
    try:
        headers={"Authorization":f"Bearer {body.api_key}"} if body.api_key else {}
        r=httpx.get(f"{normalize_url_for_docker(body.base_url).rstrip('/')}/models",headers=headers,timeout=10)
        return {"status":"ok","message":"Connected."} if r.is_success else {"status":"error","message":f"HTTP {r.status_code}"}
    except httpx.HTTPError: return {"status":"error","message":"Cannot connect to provider."}

@router.get("/providers")
def providers(user=Depends(get_current_user)):
    rows=list_ai_providers(user["user_id"])
    for row in rows: row.pop("api_key_encrypted",None)
    return {"providers":rows}
@router.get("/providers/{provider_id}")
def provider(provider_id:str,user=Depends(get_current_user)):
    row=get_ai_provider(user["user_id"],provider_id)
    if not row: raise HTTPException(404,"Provider not found")
    row.pop("api_key_encrypted",None); return row
@router.post("/providers")
def create_provider(body:ProviderCreate,user=Depends(get_current_user)):
    row=create_ai_provider(user["user_id"],body.name,normalize_url_for_docker(body.base_url),body.api_key,body.provider_type,body.provider_key,body.api_style); row.pop("api_key_encrypted",None); return row
@router.put("/providers/{provider_id}")
def edit_provider(provider_id:str,body:ProviderUpdate,user=Depends(get_current_user)):
    row=update_ai_provider(user["user_id"],provider_id,body.name,normalize_url_for_docker(body.base_url) if body.base_url else None,body.api_key,body.default_model)
    if not row: raise HTTPException(404,"Provider not found")
    row.pop("api_key_encrypted",None); return row
@router.delete("/providers/{provider_id}")
def remove_provider(provider_id:str,user=Depends(get_current_user)):
    if not delete_ai_provider(user["user_id"],provider_id): raise HTTPException(404,"Provider not found")
    return {"success":True}
@router.get("/providers/{provider_id}/models")
def models(provider_id:str,user=Depends(get_current_user)):
    row=get_ai_provider(user["user_id"],provider_id)
    if not row: raise HTTPException(404,"Provider not found")
    headers={"Authorization":f"Bearer {decrypt_api_key(row['api_key_encrypted'])}"} if row["api_key_encrypted"] else {}
    try:
        r=httpx.get(f"{row['base_url'].rstrip('/')}/models",headers=headers,timeout=10); r.raise_for_status()
        return {"models":[{"id":m["id"],"object":m.get("object","model")} for m in r.json().get("data",[])]}
    except (httpx.HTTPError,KeyError,ValueError): return {"models":[],"error":"offline"}

@router.get("/features")
def features():
    return {"features":[
        {"id":"atomic_extraction","name":"Atomic extraction","description":"Extract structured atomics from highlighted captures."},
        {"id":"entity_extraction","name":"Entity extraction","description":"Reuse and connect entity atomics."},
        {"id":"aggregate_creation","name":"Aggregate creation","description":"Name related atomic clusters."},
    ]}
@router.get("/assignments")
def assignments(user=Depends(get_current_user)): return {"assignments":list_ai_assignments(user["user_id"])}
@router.post("/assignments")
def assign(body:AssignmentSet,user=Depends(get_current_user)):
    if not get_ai_provider(user["user_id"],body.provider_id): raise HTTPException(404,"Provider not found")
    return set_ai_assignment(user["user_id"],body.feature,body.provider_id,body.model)
@router.delete("/assignments/{assignment_id}")
def unassign(assignment_id:str,user=Depends(get_current_user)):
    return {"success":delete_ai_assignment(user["user_id"],assignment_id)}

@router.post("/process-unprocessed")
def process_unprocessed(user=Depends(get_current_user)):
    captures=list_captures_without_ai_data(user["user_id"])
    for capture in captures: add_ai_job(user["user_id"],capture["id"],"atomic_extraction")
    result=start_background_batch(user["user_id"]); result["total"]=len(captures); return result
@router.post("/regenerate-all")
def regenerate_all(user=Depends(get_current_user)):
    from app.services.database import get_db
    conn=get_db(user["user_id"])
    try: conn.execute("DELETE FROM atomics"); conn.execute("DELETE FROM pending_ai_jobs"); conn.commit()
    finally: conn.close()
    return process_unprocessed(user)
@router.get("/auto-process-settings")
def auto_settings(user=Depends(get_current_user)): return {"interval_minutes":int(get_user_setting(user["user_id"],"ai_auto_process_interval","60"))}
@router.put("/auto-process-settings")
def set_auto(body:dict,user=Depends(get_current_user)):
    value=max(1,min(720,int(body.get("interval_minutes",60)))); set_user_setting(user["user_id"],"ai_auto_process_interval",str(value)); return {"interval_minutes":value}
@router.get("/pending-count")
def pending(user=Depends(get_current_user)): return {"count":count_pending_ai_jobs(user["user_id"])}
@router.post("/trigger-batch")
def trigger(user=Depends(get_current_user)): return start_background_batch(user["user_id"])
@router.get("/batch-status")
def status(user=Depends(get_current_user)): return get_batch_status(user["user_id"])
@router.get("/relation-graph")
def graph(limit:int=200,include_orphans:bool=False,include_entity_relations:bool=False,user=Depends(get_current_user)):
    return get_atomic_graph(user["user_id"],limit,include_orphans)
