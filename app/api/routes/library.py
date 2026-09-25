from fastapi import APIRouter, Depends
from app.services.auth import get_current_user
from app.services.database import (
    get_db,
    count_captures,
)

router = APIRouter()


@router.get("/api/library")
def api_library(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    stats = {
        "captures": count_captures(user_id),
    }
    conn = get_db(user_id)
    try:
        rows = conn.execute(
            "SELECT * FROM atomics ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        atomics = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("properties"), str):
                import json
                try:
                    d["properties"] = json.loads(d["properties"])
                except (json.JSONDecodeError, TypeError):
                    d["properties"] = {}
            atomics.append(d)
    except Exception:
        atomics = []
    finally:
        conn.close()

    return {
        "stats": stats,
        "atomics": atomics,
    }