"""Local first-owner setup secret. Existing accounts bypass this boundary."""
import os
import secrets
from app.core.security import CONTENTS_DIR

def setup_token():
    path = CONTENTS_DIR / ".setup_token"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as handle:
            handle.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass
    return path.read_text(encoding="utf-8").strip()

def valid_setup_token(value):
    return bool(value) and secrets.compare_digest(value, setup_token())
