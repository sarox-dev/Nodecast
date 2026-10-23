import hashlib

from app.services import database
from app.services.memory_retrieval import _candidate_search
from app.services.semantic_retrieval import EmbeddingProvider, register_embedding_provider, unregister_embedding_provider


def _fixture_embed(texts):
    vectors = []
    for text in texts:
        lowered = text.casefold()
        vectors.append([1.0, 0.0] if any(word in lowered for word in ("backup", "rezerves", "копир")) else [0.0, 1.0])
    return vectors


def test_optional_semantic_provider_enables_cross_language_fusion(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path)
    uid = "semantic-user"
    database.init_user_db(uid)
    database.insert_capture_ref(uid, "cap-ru", "snippet", "https://example.test/ru", "Резервные копии", "example.test", "", "", [], "", "")
    atomic_id = database.insert_atomic(uid, "text", "Настройте резервное копирование базы данных.", source_id="cap-ru")
    provider = EmbeddingProvider("fixture", "multilingual", "test-v1", 2, _fixture_embed)
    register_embedding_provider(provider)
    try:
        vector = _fixture_embed(["Настройте резервное копирование базы данных."])[0]
        database.upsert_atomic_embedding(uid, atomic_id, provider.provider, provider.model, provider.revision, vector, hashlib.sha256(b"fixture").hexdigest())
        results, capabilities = _candidate_search(uid, "How do I configure backups?", embedding_identity=("fixture", "multilingual"))
        assert results[0]["id"] == atomic_id
        assert results[0]["retrieval_signals"] == ["semantic"]
        assert capabilities["cross_language"] is True
    finally:
        unregister_embedding_provider("fixture", "multilingual")


def test_missing_semantic_provider_keeps_lexical_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path)
    uid = "fallback-user"
    database.init_user_db(uid)
    database.insert_capture_ref(uid, "cap", "snippet", "https://example.test", "TLS", "example.test", "", "", [], "", "")
    atomic_id = database.insert_atomic(uid, "text", "TLS certificate rotation", source_id="cap")
    results, capabilities = _candidate_search(uid, "TLS certificate", embedding_identity=("missing", "model"))
    assert results[0]["id"] == atomic_id
    assert capabilities == {"lexical": True, "cross_language": False, "semantic_reason": "provider_unavailable"}
