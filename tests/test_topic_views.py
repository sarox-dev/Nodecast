from app.services import database
from app.services.topic_views import refresh_topic_view


def test_multilingual_topic_is_rebuildable_and_source_bound(tmp_path,monkeypatch):
    monkeypatch.setattr(database,"USERS_DATA_DIR",tmp_path); uid="topics"; database.init_user_db(uid)
    for cid,text,lang in (("lv","SQLite rezerves kopijas un atjaunošana","lv"),("en","SQLite backup and restore procedure","en")):
        database.insert_capture_ref(uid,cid,"snippet",f"https://example.test/{cid}",cid,"example.test","","",[],"","")
        database.insert_atomic(uid,"text",text,properties={"language":lang,"source_span":{"capture_id":cid,"start":0,"end":len(text)}},source_id=cid)
    result=refresh_topic_view(uid,"SQLite backups",["SQLite rezerves kopijas","SQLite backup"],force=True)
    assert {item["source_id"] for item in result["evidence"]}=={"lv","en"}
    assert result["languages"]==["en","lv"]
    assert result["summary"]["kind"]=="deterministic" and result["membership_status"]=="candidate"
    conn=database.get_db(uid)
    try:
        assert conn.execute("SELECT COUNT(*) FROM atomic_relations WHERE source_atomic_id=? AND relation_type='topic_member' AND status='candidate'",(result["topic_id"],)).fetchone()[0]==2
    finally: conn.close()


def test_topic_never_promotes_derived_output_to_evidence(tmp_path,monkeypatch):
    monkeypatch.setattr(database,"USERS_DATA_DIR",tmp_path); uid="derived-topic"; database.init_user_db(uid)
    database.insert_atomic(uid,"summary","SQLite backup summary",role="aggregate",canonical_key="summary")
    result=refresh_topic_view(uid,"SQLite",["SQLite backup"],force=True)
    assert result["evidence"]==[]
