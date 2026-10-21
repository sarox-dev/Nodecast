"""AI provider configuration and atomic-pipeline controls."""
import html
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.services.ai_crypto import decrypt_api_key, normalize_url_for_docker
from app.services.chatgpt_oauth import DYNAMIC_CLIENT_ID, begin_authorization, exchange_code, get_access_token, store_tokens
from app.services.auth import get_current_user
from app.services.ai_batch import get_batch_status, start_background_batch
from app.services.database import (
    consume_ai_oauth_transaction, count_pending_ai_jobs, create_ai_provider, delete_ai_assignment, delete_ai_provider,
    get_ai_provider, get_atomic_graph, get_user_setting, list_ai_assignments,
    list_ai_providers, list_captures_without_ai_data, set_ai_assignment,
    set_user_setting, update_ai_provider, add_ai_job, get_user_by_id,
)
from app.services.outbound_security import (
    UnsafeProviderURL,
    validate_provider_destination,
)

router = APIRouter(prefix="/api/ai")


class ProviderCreate(BaseModel):
    name: str; base_url: str; api_key: str = ""; provider_type: str = "openai_compatible"; provider_key: str = ""; api_style: str = "openai"
class ProviderUpdate(BaseModel):
    name: str | None = None; base_url: str | None = None; api_key: str | None = None; default_model: str | None = None
class AssignmentSet(BaseModel):
    feature: str; provider_id: str; model: str


PROVIDER_PRESETS = [
    {"key":"chatgpt","name":"ChatGPT subscription","default_base_url":"https://api.openai.com/v1","requires_api_key":False,"api_style":"responses_oauth","oauth":True},
    {"key":"openai","name":"OpenAI","default_base_url":"https://api.openai.com/v1","requires_api_key":True,"api_style":"openai"},
    {"key":"openrouter","name":"OpenRouter","default_base_url":"https://openrouter.ai/api/v1","requires_api_key":True,"api_style":"openai"},
    {"key":"anthropic","name":"Anthropic","default_base_url":"https://api.anthropic.com/v1","requires_api_key":True,"api_style":"anthropic"},
    {"key":"gemini","name":"Google Gemini","default_base_url":"https://generativelanguage.googleapis.com/v1beta","requires_api_key":True,"api_style":"gemini"},
    {"key":"lmstudio","name":"LM Studio","default_base_url":"http://host.docker.internal:1234/v1","requires_api_key":False,"api_style":"openai"},
    {"key":"ollama","name":"Ollama","default_base_url":"http://host.docker.internal:11434/v1","requires_api_key":False,"api_style":"openai"},
    {"key":"custom","name":"Custom OpenAI Compatible","default_base_url":"","requires_api_key":False,"api_style":"openai"},
]


def _normalize_model_catalog(payload: dict, chatgpt_plan: bool = False) -> list[dict]:
    if chatgpt_plan:
        return [
            {"id": model["slug"], "name": model.get("display_name") or model["slug"], "object": "model"}
            for model in payload.get("models", [])
            if model.get("slug") and model.get("visibility") == "list"
        ]
    return [
        {"id": model["id"], "name": model.get("display_name") or model["id"], "object": model.get("object", "model")}
        for model in payload.get("data", []) if model.get("id")
    ]


def _validated_provider_url(url: str, provider_key: str, user: dict) -> str:
    account = get_user_by_id(user["user_id"])
    try:
        return validate_provider_destination(
            normalize_url_for_docker(url),
            provider_key,
            is_admin=bool(account and account["is_admin"]),
        )
    except UnsafeProviderURL as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/provider-presets")
def presets(): return {"presets": PROVIDER_PRESETS}


@router.post("/chatgpt/start")
def start_chatgpt_oauth(request: Request, user=Depends(get_current_user)):
    del request
    redirect_uri = os.getenv(
        "NODECAST_OAUTH_REDIRECT_URI",
        f"http://127.0.0.1:{os.getenv('APP_PORT', '5000')}/api/ai/chatgpt/callback",
    )
    return {"authorization_url": begin_authorization(user["user_id"], redirect_uri)}


@router.get("/chatgpt/callback", response_class=HTMLResponse)
def chatgpt_oauth_callback(
    state: str = Query(...), code: str | None = Query(None), client_id: str | None = Query(None),
    error: str | None = Query(None), error_description: str | None = Query(None),
):
    transaction = consume_ai_oauth_transaction(state)
    if not transaction:
        return HTMLResponse("<h1>Authorization expired</h1><p>Close this window and try again from Nodecast.</p>", status_code=400)
    # Dynamic registration replaces the provisional client ID with the
    # OpenAI-issued oaiapp_ ID in the callback. That issued ID must be used for
    # the token exchange and retained for later refreshes.
    if error or not code or not client_id:
        detail = html.escape(error_description or error or "Authorization was not completed")
        return HTMLResponse(f"<h1>ChatGPT was not connected</h1><p>{detail}</p>", status_code=400)
    try:
        tokens, identity = exchange_code(transaction, code, client_id)
        existing = next((p for p in list_ai_providers(transaction["user_id"]) if p.get("provider_type") == "chatgpt_oauth"), None)
        provider = existing or create_ai_provider(
            transaction["user_id"], "ChatGPT subscription", "https://api.openai.com/v1", "",
            "chatgpt_oauth", "chatgpt", "responses_oauth",
        )
        store_tokens(transaction["user_id"], provider["id"], client_id, tokens, identity)
    except (httpx.HTTPError, ValueError) as exc:
        return HTMLResponse(f"<h1>ChatGPT connection failed</h1><p>{html.escape(str(exc))}</p>", status_code=400)
    return HTMLResponse("""<!doctype html><meta charset="utf-8"><title>ChatGPT connected</title>
      <style>body{font:16px system-ui;max-width:34rem;margin:15vh auto;padding:2rem;color:#18181b}h1{font-size:1.5rem}</style>
      <h1>ChatGPT connected to Nodecast</h1><p>You can close this window and return to Settings.</p>""")

@router.post("/providers/test-connection")
def test_connection(body: ProviderCreate, user=Depends(get_current_user)):
    base_url = _validated_provider_url(body.base_url, body.provider_key, user)
    try:
        headers={"Authorization":f"Bearer {body.api_key}"} if body.api_key else {}
        r=httpx.get(f"{base_url}/models",headers=headers,timeout=10,follow_redirects=False)
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
    base_url = _validated_provider_url(body.base_url, body.provider_key, user)
    row=create_ai_provider(user["user_id"],body.name,base_url,body.api_key,body.provider_type,body.provider_key,body.api_style); row.pop("api_key_encrypted",None); return row
@router.put("/providers/{provider_id}")
def edit_provider(provider_id:str,body:ProviderUpdate,user=Depends(get_current_user)):
    existing = get_ai_provider(user["user_id"], provider_id)
    if not existing: raise HTTPException(404,"Provider not found")
    base_url = _validated_provider_url(body.base_url, existing.get("provider_key", ""), user) if body.base_url else None
    row=update_ai_provider(user["user_id"],provider_id,body.name,base_url,body.api_key,body.default_model)
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
    if row.get("provider_type") == "chatgpt_oauth":
        try:
            token = get_access_token(user["user_id"], provider_id)
            r=httpx.get("https://api.openai.com/v1/models",headers={"Authorization":f"Bearer {token}"},timeout=5); r.raise_for_status()
            return {"models":_normalize_model_catalog(r.json(), chatgpt_plan=True)}
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            return {"models":[],"error":"reconnect_required" if status in {401,403} else "provider_error","status":status}
        except (httpx.HTTPError,KeyError,TypeError,ValueError):
            return {"models":[],"error":"provider_unavailable"}
    account = get_user_by_id(user["user_id"])
    try:
        base_url = validate_provider_destination(
            row["base_url"],
            row.get("provider_key", ""),
            is_admin=bool(account and account["is_admin"]),
        )
    except UnsafeProviderURL:
        return {"models":[],"error":"unsafe_provider_url"}
    headers={"Authorization":f"Bearer {decrypt_api_key(row['api_key_encrypted'])}"} if row["api_key_encrypted"] else {}
    try:
        r=httpx.get(f"{base_url}/models",headers=headers,timeout=5,follow_redirects=False); r.raise_for_status()
        return {"models":_normalize_model_catalog(r.json())}
    except (httpx.HTTPError,KeyError,ValueError): return {"models":[],"error":"offline"}

@router.get("/features")
def features():
    return {"features":[
        {"id":"atomic_extraction","name":"Atomic extraction","description":"Extract structured atomics from highlighted captures."},
        {"id":"recall_synthesis","name":"Recall synthesis","description":"Answer questions from retrieved saved evidence with citations."},
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
    return start_background_batch(user["user_id"], "atomic_extraction")
@router.post("/regenerate-all")
def regenerate_all(user=Depends(get_current_user)):
    if get_batch_status(user["user_id"]).get("running"):
        return {"status": "already_running", "message": "AI processing is already running"}
    from app.services.database import get_db
    conn=get_db(user["user_id"])
    try: conn.execute("DELETE FROM atomics"); conn.execute("DELETE FROM pending_ai_jobs"); conn.commit()
    finally: conn.close()
    captures=list_captures_without_ai_data(user["user_id"])
    for capture in captures: add_ai_job(user["user_id"],capture["id"],"atomic_extraction")
    return start_background_batch(user["user_id"], "regenerate")
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
