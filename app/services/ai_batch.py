"""Background processing for the single atomic extraction pipeline."""
import logging
import threading

from app.services.atomic_extraction import FEATURE_ATOMIC_EXTRACTION, extract_atomics_for_capture
from app.services.database import (
    add_ai_job, count_pending_ai_jobs, get_pending_ai_jobs_grouped,
    mark_ai_job_done, mark_ai_job_error,
)

logger = logging.getLogger(__name__)
_status: dict[str, dict] = {}
_lock = threading.Lock()


def _update_progress(user_id: str, **values):
    with _lock:
        _status.setdefault(user_id, {}).update(values)


def get_batch_status(user_id: str) -> dict:
    with _lock:
        return dict(_status.get(user_id, {"running": False, "total": 0, "processed": 0, "errors": 0, "skipped": 0, "current": "", "operation": ""}))


def process_batch(user_id: str) -> dict:
    jobs = get_pending_ai_jobs_grouped(user_id)
    result = {"total": len(jobs), "processed": 0, "errors": 0, "skipped": 0}
    _update_progress(user_id, running=True, operation="atomic extraction", **result)
    while jobs:
        for job in jobs:
            try:
                response = extract_atomics_for_capture(user_id, job["capture_id"])
                if response.get("status") == "success":
                    mark_ai_job_done(user_id, job["id"]); result["processed"] += 1
                elif response.get("status") == "skipped":
                    mark_ai_job_done(user_id, job["id"]); result["skipped"] += 1
                else:
                    mark_ai_job_error(user_id, job["id"], response.get("message", "Atomic extraction failed")); result["errors"] += 1
            except Exception as exc:
                mark_ai_job_error(user_id, job["id"], str(exc)); result["errors"] += 1
                logger.exception("Atomic job failed for %s", job["capture_id"])
            _update_progress(user_id, **result, current=job["capture_id"])

        # Saves can arrive while this batch is running. Drain those jobs before
        # clearing the running flag so they do not wait for the auto interval.
        jobs = get_pending_ai_jobs_grouped(user_id)
        result["total"] = result["processed"] + result["errors"] + result["skipped"] + len(jobs)
        _update_progress(user_id, **result)
    _update_progress(user_id, running=False, operation="", **result)
    return result


def _run(user_id: str):
    try: process_batch(user_id)
    finally: _update_progress(user_id, running=False)


def start_background_batch(user_id: str) -> dict:
    if get_batch_status(user_id).get("running"):
        return {"status": "already_running"}
    threading.Thread(target=_run, args=(user_id,), daemon=True).start()
    return {"status": "started"}


def process_single(user_id: str, capture_id: str, feature: str = FEATURE_ATOMIC_EXTRACTION) -> dict:
    if feature != FEATURE_ATOMIC_EXTRACTION:
        return {"status": "error", "message": f"Unknown atomic feature: {feature}"}
    return extract_atomics_for_capture(user_id, capture_id)


def process_capture(user_id: str, capture_id: str) -> dict:
    return process_single(user_id, capture_id)


def add_pending_jobs_on_save(user_id: str, capture_id: str):
    job = add_ai_job(user_id, capture_id, FEATURE_ATOMIC_EXTRACTION)
    start_background_batch(user_id)
    return [job]


def pending_count(user_id: str) -> int:
    return count_pending_ai_jobs(user_id)
