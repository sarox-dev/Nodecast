import os

from app.services.ai_crypto import get_or_create_encryption_key

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "5000"))

# Ensure ENCRYPTION_KEY exists in .env (auto-generated if missing)
ENCRYPTION_KEY = get_or_create_encryption_key()