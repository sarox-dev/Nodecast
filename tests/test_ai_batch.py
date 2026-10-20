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


def test_start_background_batch_publishes_progress_before_thread_starts(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append((self.target, self.args, self.daemon))

    ai_batch._status.clear()
    monkeypatch.setattr(ai_batch, "count_pending_ai_jobs", lambda _uid: 7)
    monkeypatch.setattr(ai_batch.threading, "Thread", FakeThread)

    result = ai_batch.start_background_batch("user-1", "regenerate")
    status = ai_batch.get_batch_status("user-1")

    assert result == {"status": "started", "total": 7}
    assert status["running"] is True
    assert status["operation"] == "regenerate"
    assert status["total"] == 7
    assert status["pending"] == 7
    assert started[0][1] == ("user-1", "regenerate")
    ai_batch._status.clear()


def test_start_background_batch_does_not_start_duplicate_worker(monkeypatch):
    ai_batch._status.clear()
    ai_batch._status["user-1"] = {"running": True}
    monkeypatch.setattr(ai_batch, "count_pending_ai_jobs", lambda _uid: 3)

    assert ai_batch.start_background_batch("user-1") == {"status": "already_running"}
    ai_batch._status.clear()

