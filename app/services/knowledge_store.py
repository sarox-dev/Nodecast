"""
Knowledge Store — CRUD priekš knowledge_objects tabulas.

Katram userim sava knowledge_objects tabula (per-user SQLite).
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.services.database import get_db
from app.models.knowledge import KnowledgeObject, ExtractorResult


# ─── Schema init ──────────────────────────────────────────────────

def init_knowledge_schema(user_id: str | None = None):
    """Pievieno knowledge_objects tabulu usera DB. Ja user_id nav, pievieno visiem."""
    if user_id:
        _ensure_table(user_id)
    else:
        # Inicializē visiem useriem (nākotnē)
        pass


def _ensure_table(user_id: str):
    """Izveido knowledge_objects tabulu, ja vēl nav."""
    conn = get_db(user_id)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_objects (
                id TEXT PRIMARY KEY,
                capture_id TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                extracted_by TEXT DEFAULT '',
                extracted_at TEXT DEFAULT '',
                position INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_ko_capture ON knowledge_objects(capture_id);
            CREATE INDEX IF NOT EXISTS idx_ko_type ON knowledge_objects(type);
        """)
        conn.commit()
    finally:
        conn.close()


# ─── CRUD ─────────────────────────────────────────────────────────

def save_knowledge_objects(user_id: str, result: ExtractorResult):
    """Saglabā visus ExtractorResult KnowledgeObjects usera DB."""
    conn = get_db(user_id)
    try:
        _ensure_table(user_id)
        for ko in result.knowledge_objects:
            conn.execute(
                """INSERT INTO knowledge_objects
                   (id, capture_id, type, properties, confidence, extracted_by, extracted_at, position)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    ko.id,
                    ko.capture_id,
                    ko.type,
                    json.dumps(ko.properties),
                    ko.confidence,
                    ko.extracted_by,
                    ko.extracted_at,
                    ko.position,
                ),
            )
        conn.commit()
        return len(result.knowledge_objects)
    finally:
        conn.close()


def get_knowledge_for_capture(user_id: str, capture_id: str) -> list[KnowledgeObject]:
    """Atgriež visus KnowledgeObjects konkrētam capture."""
    conn = get_db(user_id)
    try:
        _ensure_table(user_id)
        rows = conn.execute(
            "SELECT * FROM knowledge_objects WHERE capture_id=? ORDER BY position ASC",
            (capture_id,),
        ).fetchall()
        return [_row_to_ko(row) for row in rows]
    finally:
        conn.close()


def get_knowledge_by_type(user_id: str, type_: str, limit: int = 50) -> list[KnowledgeObject]:
    """Atgriež KnowledgeObjects pēc tipa (piem., visus heading)."""
    conn = get_db(user_id)
    try:
        _ensure_table(user_id)
        rows = conn.execute(
            "SELECT * FROM knowledge_objects WHERE type=? ORDER BY extracted_at DESC LIMIT ?",
            (type_, limit),
        ).fetchall()
        return [_row_to_ko(row) for row in rows]
    finally:
        conn.close()


def delete_knowledge_for_capture(user_id: str, capture_id: str) -> int:
    """Dzēš visus KnowledgeObjects konkrētam capture. Atgriež skaitu."""
    conn = get_db(user_id)
    try:
        cur = conn.execute(
            "DELETE FROM knowledge_objects WHERE capture_id=?",
            (capture_id,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def count_knowledge_objects(user_id: str) -> dict:
    """Skatistika — cik kāda tipa objektu."""
    conn = get_db(user_id)
    try:
        _ensure_table(user_id)
        rows = conn.execute(
            "SELECT type, COUNT(*) as c FROM knowledge_objects GROUP BY type ORDER BY c DESC"
        ).fetchall()
        return {"by_type": {r["type"]: r["c"] for r in rows}, "total": sum(r["c"] for r in rows)}
    finally:
        conn.close()


def _row_to_ko(row) -> KnowledgeObject:
    return KnowledgeObject(
        id=row["id"],
        capture_id=row["capture_id"],
        type=row["type"],
        properties=json.loads(row["properties"]) if isinstance(row["properties"], str) else {},
        confidence=row["confidence"],
        extracted_by=row["extracted_by"],
        extracted_at=row["extracted_at"],
        position=row["position"],
    )