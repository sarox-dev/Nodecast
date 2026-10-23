#!/usr/bin/env python3
"""Start a native Nodecast installation with its persisted configuration."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def load_env(path: Path) -> None:
    """Load simple KEY=VALUE entries without evaluating shell syntax."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _ENV_KEY.fullmatch(key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def main() -> int:
    install_dir = Path(__file__).resolve().parent.parent
    os.chdir(install_dir)
    load_env(install_dir / ".env")
    os.environ["NODECAST_INSTALL_MODE"] = "host"

    try:
        port = int(os.environ.get("APP_PORT", "5000"))
    except ValueError:
        print("Nodecast: APP_PORT must be a number.", file=sys.stderr)
        return 2
    if not 1 <= port <= 65535:
        print("Nodecast: APP_PORT must be between 1 and 65535.", file=sys.stderr)
        return 2

    bind_host = os.environ.get("NODECAST_BIND_HOST", "127.0.0.1").strip()
    if bind_host not in {"127.0.0.1", "0.0.0.0"}:
        print("Nodecast: NODECAST_BIND_HOST must be 127.0.0.1 or 0.0.0.0.", file=sys.stderr)
        return 2

    import uvicorn

    uvicorn.run("app.main:app", host=bind_host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
