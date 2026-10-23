from app.services import database
from app.services.atomic_extraction import process_capture_to_atomics
from app.services.structured_extraction import extract_structured_blocks


HTML = """<!doctype html><html><body><nav>Ignore me</nav><main><h1>SQLite WAL</h1>
<p>Write-ahead logging allows readers and writers to proceed concurrently in SQLite.</p>
<h2>Checkpointing</h2><p>A checkpoint transfers committed frames from the WAL file into the database file.</p>
<pre><code>PRAGMA wal_checkpoint(TRUNCATE);</code></pre></main></body></html>"""


def test_full_page_blocks_have_verifiable_raw_spans():
    result=extract_structured_blocks(HTML,"cap")
    assert result["status"]=="indexed"
    for block in result["blocks"]:
        span=block["properties"]["source_span"]
        assert span["capture_id"]=="cap"
        assert 0 <= span["start"] < span["end"] <= len(HTML)
        assert block["properties"]["extractor_version"]=="1"


def test_full_page_creates_source_bound_atomics_without_ai(tmp_path,monkeypatch):
    monkeypatch.setattr(database,"USERS_DATA_DIR",tmp_path); uid="full-page"; database.init_user_db(uid)
    database.insert_capture_ref(uid,"cap","page","https://example.test","SQLite","example.test","","",[],"","")
    result=process_capture_to_atomics(uid,"cap",HTML,{"anchor":None})
    assert result["index_status"]=="indexed" and result["atomic_count"]>=4
    rows=database.get_atomics_by_source(uid,"cap")
    assert all(row["source_id"]=="cap" and row["properties"]["source_span"]["capture_id"]=="cap" for row in rows)


def test_weak_page_is_explicitly_not_indexed():
    result=extract_structured_blocks("<html><main><p>Short.</p></main></html>","cap")
    assert result=={"status":"saved_not_indexed","reason":"insufficient_main_content","blocks":[]}


def test_definition_list_preserves_question_and_answer_structure():
    html="<main><dl><dt>How are backups verified?</dt><dd>Restore them into an isolated database and run integrity checks before relying on them.</dd></dl></main>"
    kinds=[item["properties"]["structure_kind"] for item in extract_structured_blocks(html,"qa")["blocks"]]
    assert kinds==["question","answer"]
