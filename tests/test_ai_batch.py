from app.services import ai_batch


def test_process_batch_drains_jobs_added_while_running(monkeypatch):
    queued = [
        [{"id": "job-1", "capture_id": "capture-1"}],
        [{"id": "job-2", "capture_id": "capture-2"}],
        [],
    ]
    processed = []
    marked_done = []

    monkeypatch.setattr(ai_batch, "get_pending_ai_jobs_grouped", lambda _uid: queued.pop(0))
    monkeypatch.setattr(
        ai_batch,
        "extract_atomics_for_capture",
        lambda _uid, capture_id: processed.append(capture_id) or {"status": "success"},
    )
    monkeypatch.setattr(
        ai_batch,
        "mark_ai_job_done",
        lambda _uid, job_id: marked_done.append(job_id),
    )

    result = ai_batch.process_batch("user-1")

    assert processed == ["capture-1", "capture-2"]
    assert marked_done == ["job-1", "job-2"]
    assert result == {"total": 2, "processed": 2, "errors": 0, "skipped": 0}

