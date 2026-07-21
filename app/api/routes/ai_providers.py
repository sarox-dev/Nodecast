"""
API routes for AI provider management, feature assignments, and tagging.
"""

import json
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.auth import get_current_user
from app.services.ai_crypto import decrypt_api_key, normalize_url_for_docker
from app.services.ai_tagging import tag_capture, summarize_capture, get_available_features, FEATURE_TAGGING, FEATURE_SUMMARY
from app.services.entity_extraction import extract_entities, FEATURE_ENTITY_EXTRACTION
from app.services.ai_batch import _update_progress, get_batch_status
from app.services.database import (
    list_ai_providers,
    get_ai_provider,
    create_ai_provider,
    update_ai_provider,
    delete_ai_provider,
    list_ai_assignments,
    get_ai_assignment_for_feature,
    set_ai_assignment,
    delete_ai_assignment,
    list_captures_without_ai_tags,
    list_captures_without_ai_data,
    get_capture_ai_tags,
    upsert_capture_ai_tags,
    get_capture_ref,
    get_db,
    get_user_setting,
    set_user_setting,
)

import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai")


# ─── Models ─────────────────────────────────────────────────────────


class ProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    provider_type: str = "openai_compatible"
    provider_key: str = ""
    api_style: str = "openai"


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None


class AssignmentSet(BaseModel):
    feature: str
    provider_id: str
    model: str


# ─── Provider presets ──────────────────────────────────────────────

PROVIDER_PRESETS = [
    {"key": "openai", "name": "OpenAI", "default_base_url": "https://api.openai.com/v1", "requires_api_key": True, "api_style": "openai"},
    {"key": "openrouter", "name": "OpenRouter", "default_base_url": "https://openrouter.ai/api/v1", "requires_api_key": True, "api_style": "openai"},
    {"key": "anthropic", "name": "Anthropic", "default_base_url": "https://api.anthropic.com/v1", "requires_api_key": True, "api_style": "anthropic"},
    {"key": "gemini", "name": "Google Gemini", "default_base_url": "https://generativelanguage.googleapis.com/v1beta", "requires_api_key": True, "api_style": "gemini"},
    {"key": "lmstudio", "name": "LM Studio", "default_base_url": "http://host.docker.internal:1234/v1", "requires_api_key": False, "api_style": "openai"},
    {"key": "ollama", "name": "Ollama", "default_base_url": "http://host.docker.internal:11434/v1", "requires_api_key": False, "api_style": "openai"},
    {"key": "custom", "name": "Custom OpenAI Compatible", "default_base_url": "", "requires_api_key": False, "api_style": "openai"},
]


@router.get("/provider-presets")
def api_provider_presets():
    """Return list of available provider presets."""
    return {"presets": PROVIDER_PRESETS}


@router.post("/providers/test-connection")
def api_test_provider_connection(body: ProviderCreate):
    """Test connection to an AI provider by calling the models endpoint."""
    base_url = normalize_url_for_docker(body.base_url.rstrip("/"))
    api_key = body.api_key or ""

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{base_url}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return {"status": "ok", "message": f"Connected. {model_count} models available."}
            elif resp.status_code == 401 or resp.status_code == 403:
                return {"status": "error", "message": "Authentication failed. Check your API key."}
            elif resp.status_code == 404:
                return {"status": "error", "message": "Models endpoint not found at this URL."}
            else:
                return {"status": "error", "message": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"status": "error", "message": "Cannot connect. Check the Base URL."}
    except httpx.TimeoutException:
        return {"status": "error", "message": "Connection timed out."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


# ─── Provider CRUD ──────────────────────────────────────────────────


@router.get("/providers")
def api_list_providers(current_user: dict = Depends(get_current_user)):
    return {"providers": list_ai_providers(current_user["user_id"])}


@router.get("/providers/{provider_id}")
def api_get_provider(provider_id: str, current_user: dict = Depends(get_current_user)):
    prov = get_ai_provider(current_user["user_id"], provider_id)
    if not prov:
        raise HTTPException(404, "Provider not found")
    # Strip encrypted key — never expose it
    prov.pop("api_key_encrypted", None)
    return prov


@router.post("/providers")
def api_create_provider(body: ProviderCreate, current_user: dict = Depends(get_current_user)):
    prov = create_ai_provider(
        user_id=current_user["user_id"],
        name=body.name,
        base_url=normalize_url_for_docker(body.base_url),
        api_key_encrypted=body.api_key,
        provider_type=body.provider_type or "openai_compatible",
        provider_key=body.provider_key or "",
        api_style=body.api_style or "openai",
    )
    return prov


@router.put("/providers/{provider_id}")
def api_update_provider(provider_id: str, body: ProviderUpdate, current_user: dict = Depends(get_current_user)):
    prov = update_ai_provider(
        user_id=current_user["user_id"],
        provider_id=provider_id,
        name=body.name,
        base_url=normalize_url_for_docker(body.base_url) if body.base_url else None,
        api_key=body.api_key,
        default_model=body.default_model,
    )
    if not prov:
        raise HTTPException(404, "Provider not found")
    prov.pop("api_key_encrypted", None)
    return prov


@router.delete("/providers/{provider_id}")
def api_delete_provider(provider_id: str, current_user: dict = Depends(get_current_user)):
    if not delete_ai_provider(current_user["user_id"], provider_id):
        raise HTTPException(404, "Provider not found")
    return {"success": True}


# ─── Model list (proxy to provider endpoint) ────────────────────────


@router.get("/providers/{provider_id}/models")
def api_fetch_models(provider_id: str, current_user: dict = Depends(get_current_user)):
    prov = get_ai_provider(current_user["user_id"], provider_id)
    if not prov:
        raise HTTPException(404, "Provider not found")

    api_key = decrypt_api_key(prov.get("api_key_encrypted", ""))
    url = f"{prov['base_url'].rstrip('/')}/models"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            models = [{"id": m["id"], "object": m.get("object", "model")} for m in data.get("data", [])]
            return {"models": models}
    except httpx.ConnectError:
        raise HTTPException(502, f"Cannot connect to {prov['base_url']}")
    except httpx.TimeoutException:
        raise HTTPException(502, f"Timeout connecting to {prov['base_url']}")
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch models: {e}")


# ─── Feature assignments ────────────────────────────────────────────


@router.get("/features")
def api_list_features():
    return {"features": get_available_features()}


@router.get("/assignments")
def api_list_assignments(current_user: dict = Depends(get_current_user)):
    return {"assignments": list_ai_assignments(current_user["user_id"])}


@router.post("/assignments")
def api_set_assignment(body: AssignmentSet, current_user: dict = Depends(get_current_user)):
    # Verify provider exists
    prov = get_ai_provider(current_user["user_id"], body.provider_id)
    if not prov:
        raise HTTPException(404, "Provider not found")
    result = set_ai_assignment(
        user_id=current_user["user_id"],
        feature=body.feature,
        provider_id=body.provider_id,
        model=body.model,
    )
    return result


@router.delete("/assignments/{assignment_id}")
def api_delete_assignment(assignment_id: str, current_user: dict = Depends(get_current_user)):
    if not delete_ai_assignment(current_user["user_id"], assignment_id):
        raise HTTPException(404, "Assignment not found")
    return {"success": True}


# ─── Tagging ────────────────────────────────────────────────────────


@router.post("/tag/{capture_id}")
def api_tag_capture(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Tag a single capture with AI."""
    ref = get_capture_ref(current_user["user_id"], capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    result = tag_capture(current_user["user_id"], capture_id)
    return result


@router.post("/process-unprocessed")
def api_process_unprocessed(current_user: dict = Depends(get_current_user)):
    """Process only captures that haven't been fully processed yet (no AI tags/summary/entities).
    Runs in background with progress bar."""
    user_id = current_user["user_id"]
    unprocessed = list_captures_without_ai_data(user_id)
    if not unprocessed:
        return {"status": "done", "total": 0, "processed": 0, "message": "All captures already processed."}

    status = get_batch_status(user_id)
    if status.get("running"):
        return {"status": "already_running", "message": "AI processing is already in progress. Please wait.", "total": len(unprocessed)}

    total = len(unprocessed)
    _update_progress(user_id, running=True, total=total, processed=0, errors=0, skipped=0,
                     current="Starting process unprocessed...", operation="process unprocessed")

    thread = threading.Thread(target=_run_process_unprocessed, args=(user_id, unprocessed), daemon=True)
    thread.start()
    return {"status": "started", "total": total, "message": f"Processing {total} unprocessed capture(s) in background."}


def _run_process_unprocessed(user_id: str, captures: list[dict]):
    """Background thread: process only unprocessed captures with progress."""
    try:
        for i, cap in enumerate(captures):
            cap_errors = 0
            try:
                r = tag_capture(user_id, cap["id"])
                if r["status"] != "success" and r["status"] != "skipped":
                    cap_errors += 1
            except Exception:
                cap_errors += 1

            try:
                r = summarize_capture(user_id, cap["id"])
                if r["status"] != "success" and r["status"] != "skipped":
                    cap_errors += 1
            except Exception:
                cap_errors += 1

            try:
                r = extract_entities(user_id, cap["id"])
                if r["status"] != "success" and r["status"] != "skipped":
                    cap_errors += 1
            except Exception:
                cap_errors += 1

            if cap_errors == 0:
                _update_progress(user_id, processed=i + 1)
            else:
                _update_progress(user_id, errors=i + 1)
            _update_progress(user_id, current=f"Processing {i + 1}/{len(captures)}: {cap.get('source_title', '')[:50]}")
    except Exception as exc:
        logger.exception("Background process-unprocessed failed: %s", exc)
        _update_progress(user_id, running=False, current=f"Error: {exc}")
    finally:
        _update_progress(user_id, running=False, operation="")


@router.post("/regenerate-all")
def api_regenerate_all(current_user: dict = Depends(get_current_user)):
    """⚠ Destructive: delete ALL AI data (tags, summaries, entities) and reprocess everything."""
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        rows = conn.execute("SELECT id, source_title FROM captures").fetchall()
        captures = [{"id": r["id"], "source_title": r["source_title"] or ""} for r in rows]
    finally:
        conn.close()

    if not captures:
        return {"status": "done", "total": 0, "message": "No captures to process."}

    status = get_batch_status(user_id)
    if status.get("running"):
        return {"status": "already_running", "message": "AI processing is already in progress. Please wait.", "total": len(captures)}

    total = len(captures)
    _update_progress(user_id, running=True, total=total, processed=0, errors=0, skipped=0,
                     current="Starting regenerate-all...", operation="regenerate all")

    thread = threading.Thread(target=_run_regenerate_all, args=(user_id, captures), daemon=True)
    thread.start()
    return {"status": "started", "total": total, "message": "Regenerating all AI data in background."}


def _run_regenerate_all(user_id: str, captures: list[dict]):
    """Background thread: delete ALL AI data and reprocess everything."""
    try:
        for i, cap in enumerate(captures):
            try:
                # Delete all AI data for this capture
                conn2 = get_db(user_id)
                try:
                    conn2.execute("DELETE FROM capture_ai_tags WHERE capture_id=?", (cap["id"],))
                    conn2.execute("DELETE FROM capture_entities WHERE capture_id=?", (cap["id"],))
                    conn2.commit()
                finally:
                    conn2.close()

                # Tag
                r = tag_capture(user_id, cap["id"])
                if r["status"] != "success" and r["status"] != "skipped":
                    raise Exception(r.get("message", r.get("status", "unknown")))

                # Summarize
                r = summarize_capture(user_id, cap["id"])
                if r["status"] != "success" and r["status"] != "skipped":
                    raise Exception(r.get("message", r.get("status", "unknown")))

                # Extract entities
                r = extract_entities(user_id, cap["id"])
                if r["status"] != "success" and r["status"] != "skipped":
                    raise Exception(r.get("message", r.get("status", "unknown")))

                _update_progress(user_id, processed=i + 1)
            except Exception:
                _update_progress(user_id, errors=i + 1)
            _update_progress(user_id, current=f"Regenerating {i + 1}/{len(captures)}: {cap.get('source_title', '')[:50]}")
    except Exception as exc:
        logger.exception("Background regenerate-all failed: %s", exc)
        _update_progress(user_id, running=False, current=f"Error: {exc}")
    finally:
        _update_progress(user_id, running=False, operation="")


@router.post("/summarize/{capture_id}")
def api_summarize_capture(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Summarize a single capture with AI."""
    ref = get_capture_ref(current_user["user_id"], capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    result = summarize_capture(current_user["user_id"], capture_id)
    return result


@router.post("/extract-entities/{capture_id}")
def api_extract_entities(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Extract entities from a single capture."""
    ref = get_capture_ref(current_user["user_id"], capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")

    result = extract_entities(current_user["user_id"], capture_id)
    return result


@router.post("/process-capture/{capture_id}")
def api_process_capture(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Process ALL configured AI features for a single capture (grouped by model).
    One button in Knowledge Viewer that runs everything."""
    ref = get_capture_ref(current_user["user_id"], capture_id)
    if not ref:
        raise HTTPException(404, "Capture not found")
    from app.services.ai_batch import process_capture
    result = process_capture(current_user["user_id"], capture_id)
    return result


@router.get("/auto-process-settings")
def api_auto_process_settings(current_user: dict = Depends(get_current_user)):
    """Get auto-process interval setting (in minutes). Default 60."""
    val = get_user_setting(current_user["user_id"], "ai_auto_process_interval", "60")
    return {"interval_minutes": int(val)}


@router.put("/auto-process-settings")
def api_set_auto_process_settings(body: dict, current_user: dict = Depends(get_current_user)):
    """Set auto-process interval (in minutes). Pass {\"interval_minutes\": 15}."""
    minutes = int(body.get("interval_minutes", 60))
    minutes = max(1, min(720, minutes))  # clamp 1min–12h
    set_user_setting(current_user["user_id"], "ai_auto_process_interval", str(minutes))
    return {"interval_minutes": minutes}


@router.get("/pending-count")
def api_pending_count(current_user: dict = Depends(get_current_user)):
    """Return count of pending AI jobs."""
    from app.services.database import count_pending_ai_jobs
    return {"count": count_pending_ai_jobs(current_user["user_id"])}


@router.post("/trigger-batch")
def api_trigger_batch(current_user: dict = Depends(get_current_user)):
    """Trigger batch processing of all pending AI jobs (background, grouped by model)."""
    from app.services.ai_batch import start_background_batch
    result = start_background_batch(current_user["user_id"])
    return result


@router.get("/batch-status")
def api_batch_status(current_user: dict = Depends(get_current_user)):
    """Get current background batch processing status."""
    from app.services.ai_batch import get_batch_status
    return get_batch_status(current_user["user_id"])


@router.get("/tags/{capture_id}")
def api_get_capture_tags(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Get AI tags for a capture."""
    tags = get_capture_ai_tags(current_user["user_id"], capture_id)
    if not tags:
        return {"capture_id": capture_id, "tags": None, "has_tags": False}
    return {"capture_id": capture_id, "has_tags": True, "data": tags}


# ─── Relations ──────────────────────────────────────────────────────


@router.get("/relations/{capture_id}")
def api_get_relations(
    capture_id: str,
    min_strength: float = 0.0,
    current_user: dict = Depends(get_current_user),
):
    """Get all relations involving this capture (both as source and target)."""
    from app.services.database import get_relations_for_capture
    relations = get_relations_for_capture(current_user["user_id"], capture_id, min_strength)
    return {"capture_id": capture_id, "relations": relations, "count": len(relations)}


@router.get("/relations-entity/{entity_id}")
def api_get_entity_relations(
    entity_id: str,
    min_strength: float = 0.0,
    current_user: dict = Depends(get_current_user),
):
    """Get all relations involving this entity."""
    from app.services.database import get_relations_for_entity
    relations = get_relations_for_entity(current_user["user_id"], entity_id, min_strength)
    return {"entity_id": entity_id, "relations": relations, "count": len(relations)}


@router.get("/relation-graph")
def api_get_global_graph(
    min_strength: float = 0.0,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """Get global graph data (all nodes + edges)."""
    from app.services.database import get_relation_graph
    return get_relation_graph(current_user["user_id"], None, min_strength, limit)


@router.get("/relation-graph/{capture_id}")
def api_get_relation_graph(
    capture_id: str,
    min_strength: float = 0.0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Get graph data (nodes + edges) for a capture and its entities."""
    from app.services.database import get_relation_graph
    return get_relation_graph(current_user["user_id"], capture_id, min_strength, limit)


@router.post("/discover-relations/{capture_id}")
def api_discover_relations(
    capture_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Run Stage 1 deterministic relation discovery for this capture."""
    from app.services.relation_discovery import discover_relations
    result = discover_relations(current_user["user_id"], capture_id)
    return result


@router.post("/discover-entity-relations")
def api_discover_entity_relations(
    current_user: dict = Depends(get_current_user),
):
    """Run entity↔entity relation discovery for all entities."""
    from app.services.relation_discovery import discover_entity_relations
    count = discover_entity_relations(current_user["user_id"])
    return {"status": "success", "relations_created": count}