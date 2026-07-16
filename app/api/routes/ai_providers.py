"""
API routes for AI provider management, feature assignments, and tagging.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.auth import get_current_user
from app.services.ai_crypto import decrypt_api_key, normalize_url_for_docker
from app.services.ai_tagging import tag_capture, summarize_capture, get_available_features, FEATURE_TAGGING, FEATURE_SUMMARY
from app.services.entity_extraction import extract_entities, FEATURE_ENTITY_EXTRACTION
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
    get_capture_ai_tags,
    upsert_capture_ai_tags,
    get_capture_ref,
    get_db,
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


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None


class AssignmentSet(BaseModel):
    feature: str
    provider_id: str
    model: str


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


@router.post("/tag-all-untagged")
def api_tag_all_untagged(current_user: dict = Depends(get_current_user)):
    """Tag all captures that don't have AI tags yet."""
    untagged = list_captures_without_ai_tags(current_user["user_id"])
    if not untagged:
        return {"status": "done", "total": 0, "tagged": 0, "message": "All captures already tagged."}

    results = {"total": len(untagged), "tagged": 0, "errors": 0, "skipped": 0}
    for cap in untagged:
        try:
            r = tag_capture(current_user["user_id"], cap["id"])
            if r["status"] == "success":
                results["tagged"] += 1
            elif r["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["errors"] += 1
        except Exception:
            results["errors"] += 1

    return results


@router.post("/retag-all")
def api_retag_all(current_user: dict = Depends(get_current_user)):
    """Re-tag ALL captures. This is a dangerous operation — deletes old tags and re-runs AI on everything."""
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        rows = conn.execute("SELECT id FROM captures").fetchall()
        capture_ids = [r["id"] for r in rows]
    finally:
        conn.close()

    if not capture_ids:
        return {"status": "done", "total": 0, "tagged": 0, "message": "No captures to retag."}

    results = {"total": len(capture_ids), "tagged": 0, "errors": 0, "skipped": 0}
    for cid in capture_ids:
        try:
            # Delete old AI tags
            conn2 = get_db(user_id)
            try:
                conn2.execute("DELETE FROM capture_ai_tags WHERE capture_id=?", (cid,))
                conn2.commit()
            finally:
                conn2.close()
            r = tag_capture(user_id, cid)
            if r["status"] == "success":
                results["tagged"] += 1
            elif r["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["errors"] += 1
        except Exception:
            results["errors"] += 1

    return results


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


@router.post("/process-all")
def api_process_all_captures(current_user: dict = Depends(get_current_user)):
    """Process ALL captures: tag + summarize + extract entities.
    Only runs features that have an AI assignment configured.
    Skips captures that already have data for a given feature (unless retag is needed).
    """
    user_id = current_user["user_id"]
    conn = get_db(user_id)
    try:
        rows = conn.execute("SELECT id FROM captures").fetchall()
        capture_ids = [r["id"] for r in rows]
    finally:
        conn.close()

    if not capture_ids:
        return {"status": "done", "message": "No captures to process."}

    results = {
        "total": len(capture_ids),
        "tagged": 0,
        "summarized": 0,
        "entities_extracted": 0,
        "errors": 0,
    }

    for cid in capture_ids:
        try:
            # Tag
            r = tag_capture(user_id, cid)
            if r["status"] == "success":
                results["tagged"] += 1
        except Exception:
            results["errors"] += 1

        try:
            # Summarize
            r = summarize_capture(user_id, cid)
            if r["status"] == "success":
                results["summarized"] += 1
        except Exception:
            results["errors"] += 1

        try:
            # Extract entities
            r = extract_entities(user_id, cid)
            if r["status"] == "success":
                results["entities_extracted"] += 1
        except Exception:
            results["errors"] += 1

    return results


@router.get("/tags/{capture_id}")
def api_get_capture_tags(capture_id: str, current_user: dict = Depends(get_current_user)):
    """Get AI tags for a capture."""
    tags = get_capture_ai_tags(current_user["user_id"], capture_id)
    if not tags:
        return {"capture_id": capture_id, "tags": None, "has_tags": False}
    return {"capture_id": capture_id, "has_tags": True, "data": tags}