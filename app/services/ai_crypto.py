"""
Fernet-based encryption for AI provider API keys.
Uses ENCRYPTION_KEY from .env — auto-generated if missing.
"""

import os
import base64
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ─── Key management ─────────────────────────────────────────────────

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
ENCRYPTION_KEY_VAR = "ENCRYPTION_KEY"


def _load_env() -> dict[str, str]:
    """Load .env file into a dict (simple parser, no deps)."""
    env = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


def _write_env_var(key: str, value: str):
    """Append or replace a key=value in .env."""
    existing = _load_env()
    existing[key] = value
    lines = []
    found = False
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from a passphrase using PBKDF2."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def get_or_create_encryption_key() -> str:
    """Get the existing ENCRYPTION_KEY from .env, or generate a new one."""
    env = _load_env()
    key = env.get(ENCRYPTION_KEY_VAR, "")
    if key:
        return key
    # Generate a new Fernet key
    import secrets
    key = Fernet.generate_key().decode()
    _write_env_var(ENCRYPTION_KEY_VAR, key)
    return key


def get_fernet() -> Fernet:
    """Get a Fernet instance from the ENCRYPTION_KEY in .env."""
    key_str = get_or_create_encryption_key()
    return Fernet(key_str.encode())


# ─── Encrypt / Decrypt ──────────────────────────────────────────────

def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key (or empty string). Returns base64-encoded ciphertext."""
    if not plaintext:
        return ""
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt an API key. Returns empty string if ciphertext is empty."""
    if not ciphertext:
        return ""
    f = get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


# ─── Docker host detection ──────────────────────────────────────────

def _is_running_in_docker() -> bool:
    """Detect if we're running inside a Docker container."""
    try:
        if Path("/.dockerenv").exists():
            return True
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists() and "docker" in cgroup.read_text():
            return True
    except Exception:
        pass
    return False


_IN_DOCKER = _is_running_in_docker()
_HOST_GATEWAY = "host.docker.internal"


def normalize_url_for_docker(url: str) -> str:
    """Rewrite localhost/127.0.0.1 to host.docker.internal when inside Docker."""
    if not _IN_DOCKER:
        return url
    # Replace localhost and 127.0.0.1 with host.docker.internal
    import re
    url = re.sub(r'://localhost(?=:\d+)', f'://{_HOST_GATEWAY}', url)
    url = re.sub(r'://127\.0\.0\.1(?=:\d+)', f'://{_HOST_GATEWAY}', url)
    return url