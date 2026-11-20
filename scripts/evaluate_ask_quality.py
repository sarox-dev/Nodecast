#!/usr/bin/env python3
"""Evaluate the final local Ask packet using only an isolated synthetic corpus."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services import database
from app.services.memory_retrieval import query_memory

DEFAULT_CORPUS = REPO_ROOT / "tests/fixtures/ask_quality_corpus.json"


def load_corpus(path=DEFAULT_CORPUS):
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = [row["id"] for row in corpus["captures"]]
    keys = [key for row in corpus["captures"] for key, _text in row["evidence"]]
    source_for_key = {key: row["id"] for row in corpus["captures"] for key, _text in row["evidence"]}
    queries = [row["id"] for row in corpus["queries"]]
    for values in (sources, keys, queries):
        if len(values) != len(set(values)):
            raise ValueError("Corpus IDs and evidence keys must be unique")
    for row in corpus["queries"]:
        if not set(row["expected_sources"]) <= set(sources) or not set(row.get("forbidden_sources", [])) <= set(sources):
            raise ValueError("Unknown corpus source")
        if not set(row["expected"]) <= set(keys):
            raise ValueError("Unknown corpus evidence")
        if set(row["expected_sources"]) != {source_for_key[key] for key in row["expected"]}:
            raise ValueError("Expected evidence must belong to the expected sources")
        if not 1 <= row.get("limit", 8) <= 8 or not 100 <= row.get("token_budget", 700) <= 4000:
            raise ValueError("Corpus packet bounds must match the Ask API")
    return corpus


@contextmanager
def isolated_database():
    previous = (database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR)
    with tempfile.TemporaryDirectory(prefix="nodecast-ask-quality-") as name:
        root = Path(name)
        database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR = root, root / "users.db", root / "users"
        try:
            yield
        finally:
            database.CONTENTS_DIR, database.USERS_DB_PATH, database.USERS_DATA_DIR = previous


def _mean(values):
    defined = [value for value in values if value is not None]
    return round(statistics.mean(defined), 4) if defined else None


def score_packet(cards, expected_sources, expected_evidence, evidence_by_id):
    # Source precision uses unique source IDs, never the number of evidence rows.
    sources = list(dict.fromkeys(item["source_id"] for item in cards))
    selected = {item["id"] for item in cards}
    expected_sources, expected_evidence = set(expected_sources), set(expected_evidence)
    top5 = set(sources[:5])
    valid = []
    for item in cards:
        original = evidence_by_id.get(item["id"])
        valid.append(bool(original and item["source_id"] == original["source_id"]
                          and item["source_url"] == original["url"]
                          and item["excerpt"] == original["text"][:700]))
    return {
        "actual_sources": sources,
        "source_recall_at_5": len(top5 & expected_sources) / len(expected_sources) if expected_sources else None,
        "source_recall_in_packet": len(set(sources) & expected_sources) / len(expected_sources) if expected_sources else None,
        "source_precision_at_5": len(top5 & expected_sources) / len(top5) if top5 else None,
        "evidence_recall_in_packet": len(selected & expected_evidence) / len(expected_evidence) if expected_evidence else None,
        "evidence_precision_in_packet": len(selected & expected_evidence) / len(selected) if selected else None,
        "provenance_integrity": all(valid),
    }


def evaluate_corpus(corpus):
    with isolated_database():
        uid = database.create_user_in_db("ask-quality-member", "synthetic-not-a-password-hash")
        evidence_keys, evidence_by_id = {}, {}
        for source in corpus["captures"]:
            url = "https://example.invalid/" + source["id"]
            database.insert_capture_ref(uid, source["id"], "snippet", url, source["title"], "example.invalid", "", "", [], "", "")
            for position, (key, text) in enumerate(source["evidence"]):
                ident = database.insert_atomic(uid, "text", text, source_id=source["id"], context_header=source["title"], position=position)
                evidence_keys[key] = ident
                evidence_by_id[ident] = {"key": key, "source_id": source["id"], "url": url, "text": text}
                if source.get("rejected"):
                    connection = database.get_db(uid)
                    try:
                        connection.execute("UPDATE atomics SET status='rejected' WHERE id=?", (ident,))
                        connection.commit()
                    finally:
                        connection.close()
        rows, latencies = [], []
        for case in corpus["queries"]:
            started = time.perf_counter()
            result = query_memory(uid, case["query"], limit=case.get("limit", 8), token_budget=case.get("token_budget", 700), synthesize=False)
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            cards = result["items"]
            scored = score_packet(cards, case["expected_sources"], [evidence_keys[key] for key in case["expected"]], evidence_by_id)
            rows.append({
                "id": case["id"], "query": case["query"], "kind": case.get("kind", "lookup"),
                "expected_sources": case["expected_sources"], **scored,
                "actual_evidence_keys": [evidence_by_id[item["id"]]["key"] for item in cards],
                "forbidden_source_hits": sorted(set(scored["actual_sources"]) & set(case.get("forbidden_sources", []))),
                "selected_evidence_count": len(cards), "token_estimate": result["token_estimate"],
                "limit": case.get("limit", 8), "token_budget": case.get("token_budget", 700),
                "latency_ms": round(elapsed, 2),
            })
        names = ("source_recall_at_5", "source_recall_in_packet", "source_precision_at_5", "evidence_recall_in_packet", "evidence_precision_in_packet")
        return {
            "corpus_version": corpus["version"],
            "corpus_sha256": hashlib.sha256(json.dumps(corpus, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "pipeline": "query_memory(synthesize=False)",
            "scope": "Synthetic local Ask evidence selection only; no capture/indexing, authenticated browser, AI answer or semantic citation-support evaluation.",
            "retrieval_sha256": hashlib.sha256((REPO_ROOT / "app/services/memory_retrieval.py").read_bytes()).hexdigest(),
            "source_at_5_definition": "Top five distinct sources in packet order, not the first five evidence rows; recall undefined for empty ground truth, precision undefined for empty results",
            "captures": len(corpus["captures"]), "queries": len(rows),
            "metrics": {name: _mean([row[name] for row in rows]) for name in names} | {
                "provenance_integrity": all(row["provenance_integrity"] for row in rows),
                "queries_with_forbidden_sources": sum(bool(row["forbidden_source_hits"]) for row in rows),
            },
            "latency_ms": {"p50": round(statistics.median(latencies), 2), "max": round(max(latencies), 2)},
            "results": rows,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(evaluate_corpus(load_corpus(args.corpus)), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
