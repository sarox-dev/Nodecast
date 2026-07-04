import os
from pathlib import Path

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "72"))  # 3 dienas

# Auto-generate JWT secret if not set
if not JWT_SECRET:
    import secrets
    _secret_path = Path(__file__).resolve().parent.parent.parent / "contents" / ".jwt_secret"
    if _secret_path.exists():
        JWT_SECRET = _secret_path.read_text().strip()
    else:
        JWT_SECRET = secrets.token_hex(32)
        _secret_path.parent.mkdir(parents=True, exist_ok=True)
        _secret_path.write_text(JWT_SECRET)

# Paths
CONTENTS_DIR = Path(__file__).resolve().parent.parent.parent / "contents"
USERS_DB_PATH = CONTENTS_DIR / "users.db"
USERS_DATA_DIR = CONTENTS_DIR / "users"