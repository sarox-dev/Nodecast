"""
Auto Processor — background scheduler for AI processing on the server side.

Runs in a daemon thread, checks all users' settings for auto_process_interval,
and calls process_unprocessed for each user that has it enabled.

Started on application startup from main.py.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# ─── Globals ───────────────────────────────────────────────────────

_processor_thread: threading.Thread | None = None
_running = False
_CHECK_INTERVAL = 30  # seconds between user checks

# ─── Core loop ─────────────────────────────────────────────────────


def _get_all_user_ids() -> list[str]:
    """Get all user IDs from the global users database."""
    from app.services.database import get_users_db

    conn = get_users_db()
    try:
        rows = conn.execute("SELECT id FROM users").fetchall()
        return [r["id"] for r in rows]
    finally:
        conn.close()


def _process_for_user(user_id: str):
    """Run process-unprocessed for a user if their interval timer is up."""
    from app.services.database import get_user_setting, get_db

    # Get the interval setting (in minutes)
    try:
        interval_str = get_user_setting(user_id, "ai_auto_process_interval", "60")
        interval_minutes = int(interval_str)
    except (ValueError, Exception):
        interval_minutes = 60

    if interval_minutes <= 0:
        return  # Disabled

    # Check when we last ran for this user (stored in-memory or in DB)
    last_key = f"ai_last_process_time_{user_id}"
    now = int(time.time())
    last_time = getattr(_processor_thread, last_key, 0)

    if now - last_time < interval_minutes * 60:
        return  # Not time yet

    # Time to run — mark and execute
    setattr(_processor_thread, last_key, now)

    try:
        # Check if batch is already running for this user
        from app.services.ai_batch import get_batch_status

        status = get_batch_status(user_id)
        if status.get("running"):
            logger.debug("Auto-process: user %s already running, skipping", user_id[:8])
            return

        # Find unprocessed captures
        from app.services.database import list_captures_without_ai_data

        unprocessed = list_captures_without_ai_data(user_id)
        if not unprocessed:
            return  # Nothing to do

        logger.info(
            "Auto-process: user %s has %d unprocessed capture(s), starting...",
            user_id[:8],
            len(unprocessed),
        )

        # Process them in background thread
        from app.services.ai_tagging import tag_capture, summarize_capture
        from app.services.entity_extraction import extract_entities
        from app.services.ai_batch import _update_progress

        total = len(unprocessed)
        _update_progress(
            user_id,
            running=True,
            total=total,
            processed=0,
            errors=0,
            skipped=0,
            current="Starting auto-process...",
            operation="auto process",
        )

        def _run():
            try:
                for i, cap in enumerate(unprocessed):
                    cap_errors = 0
                    try:
                        r = tag_capture(user_id, cap["id"])
                        if r["status"] not in ("success", "skipped"):
                            cap_errors += 1
                    except Exception:
                        cap_errors += 1

                    try:
                        r = summarize_capture(user_id, cap["id"])
                        if r["status"] not in ("success", "skipped"):
                            cap_errors += 1
                    except Exception:
                        cap_errors += 1

                    try:
                        r = extract_entities(user_id, cap["id"])
                        if r["status"] not in ("success", "skipped"):
                            cap_errors += 1
                    except Exception:
                        cap_errors += 1

                    if cap_errors == 0:
                        _update_progress(user_id, processed=i + 1)
                    else:
                        _update_progress(user_id, errors=i + 1)
                    _update_progress(
                        user_id,
                        current=f"Auto {i + 1}/{total}: {cap.get('source_title', '')[:40]}",
                    )
            except Exception as exc:
                logger.exception("Auto-process run failed for user %s: %s", user_id[:8], exc)
                _update_progress(user_id, running=False, current=f"Error: {exc}")
            finally:
                _update_progress(user_id, running=False, operation="")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    except Exception as exc:
        logger.error("Auto-process error for user %s: %s", user_id[:8], exc)


def _loop():
    """Main loop — check all users periodically."""
    global _running
    _running = True
    logger.info("Auto-processor started (check interval: %ds)", _CHECK_INTERVAL)

    while _running:
        try:
            user_ids = _get_all_user_ids()
            for uid in user_ids:
                _process_for_user(uid)
        except Exception as exc:
            logger.error("Auto-processor loop error: %s", exc)
        time.sleep(_CHECK_INTERVAL)

    logger.info("Auto-processor stopped")


def start_auto_processor():
    """Start the background auto-processor daemon thread. Safe to call multiple times."""
    global _processor_thread
    if _processor_thread and _processor_thread.is_alive():
        logger.debug("Auto-processor already running")
        return
    _processor_thread = threading.Thread(target=_loop, daemon=True)
    _processor_thread.start()


def stop_auto_processor():
    """Gracefully stop the auto-processor on next interval."""
    global _running
    _running = False
