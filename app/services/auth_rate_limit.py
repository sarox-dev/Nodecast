"""Small process-local limiter for authentication and reauthentication attempts."""
import threading
import time

from fastapi import HTTPException, Request

WINDOW_SECONDS = 300
MAX_ATTEMPTS = 8

_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()


def rate_key(request: Request, action: str, subject: str = "") -> str:
    client = request.client.host if request.client else "unknown"
    return f"{action}:{client}:{subject.casefold()}"


def check_rate_limit(*keys: str) -> None:
    now = time.monotonic()
    with _lock:
        for existing_key in list(_attempts):
            recent = [stamp for stamp in _attempts[existing_key] if now - stamp < WINDOW_SECONDS]
            if recent:
                _attempts[existing_key] = recent
            else:
                _attempts.pop(existing_key, None)
        if any(len(_attempts.get(key, [])) >= MAX_ATTEMPTS for key in keys):
            raise HTTPException(429, "Too many authentication attempts. Try again later.")


def record_failure(*keys: str) -> None:
    now = time.monotonic()
    with _lock:
        for key in keys:
            _attempts.setdefault(key, []).append(now)


def clear_failures(*keys: str) -> None:
    with _lock:
        for key in keys:
            _attempts.pop(key, None)
