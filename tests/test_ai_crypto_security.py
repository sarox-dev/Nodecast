from cryptography.fernet import Fernet

from app.services import ai_crypto


def test_generated_encryption_key_is_persisted_in_contents(tmp_path, monkeypatch):
    key_path = tmp_path / "contents" / ".encryption_key"
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(ai_crypto, "PERSISTED_KEY_PATH", key_path)
    monkeypatch.setattr(ai_crypto, "_load_env", lambda: {})

    first = ai_crypto.get_or_create_encryption_key()
    second = ai_crypto.get_or_create_encryption_key()

    Fernet(first.encode())
    assert second == first
    assert key_path.read_text() == first


def test_environment_encryption_key_keeps_existing_install_compatible(tmp_path, monkeypatch):
    configured = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", configured)
    monkeypatch.setattr(ai_crypto, "PERSISTED_KEY_PATH", tmp_path / "missing")
    assert ai_crypto.get_or_create_encryption_key() == configured
