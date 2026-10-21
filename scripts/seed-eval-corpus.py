#!/usr/bin/env python3
"""Seed the curated recall-evaluation captures for one local Nodecast user.

This is intentionally deterministic-only: it creates immutable Raw Captures and
source-bound evidence without spending a user's AI-provider quota.
"""
import argparse
import html
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.atomic_extraction import split_evidence
from app.services.atomic_relations import discover_relations_for_capture
from app.services.database import (
    get_capture_ref,
    get_user_by_username,
    insert_atomic_relation,
    insert_atomics_batch,
    insert_capture_ref,
)
from app.models.capture_package import Anchor, CapturePackage, SourceInfo
from app.services.raw_storage import save_raw_capture


CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "gold_recall_corpus.json"


def snapshot(item: dict) -> str:
    return """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{title}</title></head>
<body><main><h1>{title}</h1><p><a href=\"{url}\">Original source</a></p><article><p>{text}</p></article></main></body></html>""".format(
        title=html.escape(item["title"]), url=html.escape(item["url"], quote=True), text=html.escape(item["text"])
    )


def seed(username: str) -> dict:
    user = get_user_by_username(username.strip().lower())
    if not user:
        raise SystemExit(f"User not found: {username}")
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    created, skipped = [], []
    for item in corpus["captures"]:
        capture_id = item["id"]
        if get_capture_ref(user["id"], capture_id):
            skipped.append(capture_id)
            continue
        package = CapturePackage(
            capture_id=capture_id,
            capture_type="snippet",
            source=SourceInfo(url=item["url"], title=item["title"], site_name=item["site"]),
            anchor=Anchor(selected_text=item["text"], selected_tag="p"),
            tags=item["tags"], project="Nodecast retrieval evaluation corpus",
        )
        raw_path = save_raw_capture(user["id"], package, html=snapshot(item))
        insert_capture_ref(
            user["id"], capture_id, package.capture_type, item["url"], item["title"], item["site"],
            package.captured_at, package.captured_at, item["tags"], package.project, str(raw_path),
        )
        evidence = split_evidence(item["text"], item["title"])
        for row in evidence:
            row.update({"role": "evidence", "source_id": capture_id, "extracted_by": "eval-deterministic", "status": "ready"})
        ids = insert_atomics_batch(user["id"], evidence)
        for index, atomic_id in enumerate(ids):
            if index:
                insert_atomic_relation(
                    user["id"], ids[index - 1], atomic_id, "precedes", 1.0,
                    method="structural", reason="Adjacent evaluation evidence", confidence=1.0, status="accepted",
                )
        discover_relations_for_capture(user["id"], capture_id)
        created.append(capture_id)
    return {"user": user["username"], "created": created, "skipped": skipped, "total": len(corpus["captures"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Nodecast's curated local retrieval corpus.")
    parser.add_argument("--username", required=True)
    print(json.dumps(seed(parser.parse_args().username), ensure_ascii=False, indent=2))
