from app.services import database


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path)
    uid="jobs-user"; database.init_user_db(uid)
    database.insert_capture_ref(uid,"cap","snippet","","","","","",[],"","")
    return uid


def test_jobs_are_idempotent_and_leased_atomically(tmp_path, monkeypatch):
    uid=_db(tmp_path,monkeypatch)
    first=database.add_ai_job(uid,"cap","atomic_extraction","input-v1","processor-v1")
    second=database.add_ai_job(uid,"cap","atomic_extraction","input-v1","processor-v1")
    assert first==second
    assert database.lease_ai_job(uid,first["id"],"worker-a",60) is True
    assert database.lease_ai_job(uid,first["id"],"worker-b",60) is False
    conn=database.get_db(uid)
    try:
        row=conn.execute("SELECT status,attempt_count,lease_owner FROM pending_ai_jobs WHERE id=?",(first["id"],)).fetchone()
        assert tuple(row)==("processing",1,"worker-a")
    finally: conn.close()


def test_failed_job_retries_then_becomes_terminal(tmp_path, monkeypatch):
    uid=_db(tmp_path,monkeypatch); job=database.add_ai_job(uid,"cap","atomic_extraction")
    assert database.lease_ai_job(uid,job["id"],"worker")
    assert database.retry_or_fail_ai_job(uid,job["id"],"boom","failure",base_delay_seconds=1)=="pending"
    conn=database.get_db(uid)
    try:
        conn.execute("UPDATE pending_ai_jobs SET next_retry_at='',attempt_count=2 WHERE id=?",(job["id"],)); conn.commit()
    finally: conn.close()
    assert database.lease_ai_job(uid,job["id"],"worker")
    assert database.retry_or_fail_ai_job(uid,job["id"],"boom","failure",base_delay_seconds=1)=="error"
