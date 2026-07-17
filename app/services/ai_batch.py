"""
Batch Processor — groups pending AI jobs by (provider_id, model)
so each model is loaded only once per batch cycle.

Provides:
  - process_batch(user_id)        — batch-process all pending jobs
  - process_single(user_id, cap, feature) — process one capture immediately
  - add_pending_jobs_on_save(uid, cap_id) — enqueue all configured features
"""

import logging
import threading
from datetime import datetime, timezone

# ─── Background batch status (in-memory, per-user) ────────────────
_batch_status: dict[str, dict] = {}
_batch_lock = threading.Lock()


def _update_progress(user_id: str, **kwargs):
    with _batch_lock:
        if user_id not in _batch_status:
            _batch_status[user_id] = {}
        _batch_status[user_id].update(kwargs)


def get_batch_status(user_id: str) -> dict:
    with _batch_lock:
        return _batch_status.get(user_id, {
            "running": False, "total": 0, "processed": 0,
            "errors": 0, "skipped": 0, "current": "",
        })


def start_background_batch(user_id: str) -> dict:
    """Start batch processing in a background daemon thread."""
    with _batch_lock:
        existing = _batch_status.get(user_id, {})
        if existing.get("running"):
            return {"status": "already_running"}
    thread = threading.Thread(target=_run_batch_thread, args=(user_id,), daemon=True)
    thread.start()
    return {"status": "started"}


def _run_batch_thread(user_id: str):
    """Run process_batch in a thread and clear status when done."""
    try:
        process_batch(user_id)
    except Exception as exc:
        _update_progress(user_id, running=False, current=f"Error: {exc}")
        logger.exception("Background batch failed for user %s", user_id)
    finally:
        _update_progress(user_id, running=False)


from app.services.ai_tagging import (
    tag_capture,
    summarize_capture,
    FEATURE_TAGGING,
    FEATURE_SUMMARY,
)
from app.services.entity_extraction import (
    extract_entities,
    FEATURE_ENTITY_EXTRACTION,
)
from app.services.database import (
    get_pending_ai_jobs_grouped,
    mark_ai_job_done,
    mark_ai_job_error,
    add_ai_job,
    count_pending_ai_jobs,
    list_ai_assignments,
)

logger = logging.getLogger(__name__)

# ─── Feature dispatch map ──────────────────────────────────────────
# Maps feature name → (handler function, feature constant)
FEATURE_MAP = {
    "tagging": (tag_capture, FEATURE_TAGGING),
    "summary": (summarize_capture, FEATURE_SUMMARY),
    "entity_extraction": (extract_entities, FEATURE_ENTITY_EXTRACTION),
}

# ─── Batch processing ──────────────────────────────────────────────


def process_batch(user_id: str) -> dict:
    """Process all pending AI jobs for *user_id*, grouped by model.

    Jobs are already ordered by (provider_id, model, created_at) from
    ``get_pending_ai_jobs_grouped``.  We iterate group-by-group so each
    model is only loaded once per batch run.

    Returns
    -------
    dict with keys: total, processed, errors, skipped
    """
    jobs = get_pending_ai_jobs_grouped(user_id)
    total = len(jobs)
    processed = 0
    errors = 0
    skipped = 0

    if not jobs:
        logger.info("No pending AI jobs for user %s", user_id)
        return {"total": 0, "processed": 0, "errors": 0, "skipped": 0}

    logger.info(
        "Batch processing %d pending AI jobs for user %s (grouped by model)",
        total,
        user_id,
    )

    # Group jobs by (provider_id, model)
    groups: dict[tuple[str, str], list[dict]] = {}
    for job in jobs:
        key = (job["provider_id"], job["model"])
        groups.setdefault(key, []).append(job)

    for (provider_id, model), group_jobs in groups.items():
        logger.info(
            "Processing group provider=%s model=%s (%d jobs)",
            provider_id,
            model,
            len(group_jobs),
        )

        for job in group_jobs:
            feature = job["feature"]
            capture_id = job["capture_id"]
            job_id = job["id"]

            handler = FEATURE_MAP.get(feature)
            if handler is None:
                logger.warning(
                    "Unknown feature '%s' for job %s — skipping",
                    feature,
                    job_id,
                )
                mark_ai_job_error(
                    user_id, job_id, error=f"Unknown feature: {feature}"
                )
                skipped += 1
                continue

            func, _ = handler
            try:
                result = func(user_id, capture_id)
                status = result.get("status", "unknown")

                if status == "success":
                    mark_ai_job_done(user_id, job_id)
                    processed += 1
                    _update_progress(user_id, processed=processed, errors=errors, skipped=skipped, current=f"{feature} on {capture_id[:8]}...")
                    logger.info(
                        "Job %s | capture=%s | feature=%s | status=%s",
                        job_id,
                        capture_id,
                        feature,
                        status,
                    )
                elif status == "no_assignment":
                    # No provider configured for this feature — skip
                    mark_ai_job_error(
                        user_id,
                        job_id,
                        error=f"No assignment configured for feature '{feature}'",
                    )
                    skipped += 1
                    logger.warning(
                        "Job %s | capture=%s | feature=%s | no assignment, skipping",
                        job_id,
                        capture_id,
                        feature,
                    )
                elif status == "skipped":
                    # Handler indicated the job was a no-op (e.g. capture gone)
                    mark_ai_job_done(user_id, job_id)
                    skipped += 1
                    logger.info(
                        "Job %s | capture=%s | feature=%s | skipped (no-op)",
                        job_id,
                        capture_id,
                        feature,
                    )
                else:
                    # Any other status (including 'error')
                    err_msg = result.get("message", result.get("error", status))
                    mark_ai_job_error(
                        user_id, job_id, error=str(err_msg)[:500]
                    )
                    errors += 1
                    logger.error(
                        "Job %s | capture=%s | feature=%s | error: %s",
                        job_id,
                        capture_id,
                        feature,
                        err_msg,
                    )
            except Exception as exc:
                mark_ai_job_error(user_id, job_id, error=str(exc)[:500])
                errors += 1
                logger.exception(
                    "Job %s | capture=%s | feature=%s | unhandled exception: %s",
                    job_id,
                    capture_id,
                    feature,
                    exc,
                )

    # Clear any sub-dictionaries left behind by the function name
    del groups

    summary = {
        "total": total,
        "processed": processed,
        "errors": errors,
        "skipped": skipped,
    }
    logger.info(
        "Batch complete for user %s: %s",
        user_id,
        summary,
    )
    return summary


# ─── Single job (manual / Knowledge Viewer) ───────────────────────


def process_single(user_id: str, capture_id: str, feature: str) -> dict:
    """Process a single capture+feature immediately (e.g. from Knowledge
    Viewer manual buttons).

    Returns the raw result dict from the underlying handler.
    """
    handler = FEATURE_MAP.get(feature)
    if handler is None:
        logger.warning("Unknown feature '%s' for single job", feature)
        return {"status": "error", "message": f"Unknown feature: {feature}"}

    func, _ = handler
    logger.info(
        "Processing single job | user=%s capture=%s feature=%s",
        user_id,
        capture_id,
        feature,
    )
    try:
        result = func(user_id, capture_id)
        logger.info(
            "Single job done | user=%s capture=%s feature=%s status=%s",
            user_id,
            capture_id,
            feature,
            result.get("status", "unknown"),
        )
        return result
    except Exception as exc:
        logger.exception(
            "Single job failed | user=%s capture=%s feature=%s | %s",
            user_id,
            capture_id,
            feature,
            exc,
        )
        return {"status": "error", "message": str(exc)}


# ─── Enqueue jobs on save ─────────────────────────────────────────


def process_capture(user_id: str, capture_id: str) -> dict:
    """Process ALL configured AI features for a single capture, grouped by model.
    Loads each model only once, running all features that use it sequentially.

    Used by the Knowledge Viewer "AI Analysis" button.

    Returns
    -------
    dict with keys: results (per-feature), errors, total
    """
    from app.services.database import list_ai_assignments

    assignments = list_ai_assignments(user_id)
    if not assignments:
        return {"status": "no_assignment", "message": "No AI features configured. Go to Settings → AI.", "results": []}

    # Group assignments by (provider_id, model)
    groups: dict[tuple[str, str], list[dict]] = {}
    for a in assignments:
        feature = a.get("feature", "")
        if feature not in FEATURE_MAP:
            continue
        key = (a["provider_id"], a["model"])
        groups.setdefault(key, []).append(a)

    if not groups:
        return {"status": "no_assignment", "message": "No supported AI features configured.", "results": []}

    results = []
    errors = 0

    for (provider_id, model), group_assignments in groups.items():
        logger.info(
            "Processing capture=%s with model=%s (%d features)",
            capture_id, model, len(group_assignments),
        )
        for assignment in group_assignments:
            feature = assignment["feature"]
            handler = FEATURE_MAP.get(feature)
            if handler is None:
                continue
            func, _ = handler
            try:
                result = func(user_id, capture_id)
                status = result.get("status", "unknown")
                results.append({"feature": feature, "status": status, "result": result})
                if status == "error":
                    errors += 1
                    logger.warning("process_capture: %s → error: %s", feature, result.get("message", result.get("status", "unknown")))
                else:
                    logger.info("process_capture: %s → %s", feature, status)
            except Exception as exc:
                logger.exception("process_capture: feature=%s failed: %s", feature, exc)
                results.append({"feature": feature, "status": "error", "message": str(exc)})
                errors += 1

    logger.info("process_capture done: %d/%d ok, %d errors", len(results) - errors, len(results), errors)

    return {"results": results, "errors": errors, "total": len(results)}


def add_pending_jobs_on_save(user_id: str, capture_id: str):
    """Called when a capture is saved.  Adds pending AI jobs for *all*
    features that have a valid ``ai_feature_assignments`` entry.

    Each job will be picked up by the next ``process_batch`` call.
    """
    assignments = list_ai_assignments(user_id)
    if not assignments:
        logger.debug(
            "No AI assignments configured for user %s — nothing to enqueue",
            user_id,
        )
        return

    enqueued = 0
    for assignment in assignments:
        feature = assignment.get("feature")
        if not feature or feature not in FEATURE_MAP:
            logger.debug(
                "Skipping unknown/unhandled feature '%s' in assignment",
                feature,
            )
            continue
        add_ai_job(user_id, capture_id, feature)
        enqueued += 1

    if enqueued:
        remaining = count_pending_ai_jobs(user_id)
        logger.info(
            "Enqueued %d AI job(s) for capture=%s (total pending: %d)",
            enqueued,
            capture_id,
            remaining,
        )
    else:
        logger.debug(
            "No supported features in assignments for capture=%s", capture_id
        )
