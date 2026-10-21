#!/usr/bin/env python3
"""Measure deterministic retrieval against the curated Nodecast gold corpus."""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.database import get_user_by_username
from app.services.memory_retrieval import _memory_context


CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "gold_recall_corpus.json"


def evaluate(username: str) -> dict:
    user = get_user_by_username(username.strip().lower())
    if not user:
        raise SystemExit(f"User not found: {username}")
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    rows, latencies, recalls, precisions, packet_tokens = [], [], [], [], []
    for test in corpus["queries"]:
        started = time.perf_counter()
        result, _packet, _intent = _memory_context(user["id"], test["query"], 5, 700, "auto")
        elapsed = (time.perf_counter() - started) * 1000
        actual = [item.get("source_id") for item in result["items"] if item.get("source_id")]
        expected = set(test["expected"])
        hit_count = len(expected.intersection(actual))
        recall = hit_count / len(expected)
        precision = hit_count / len(actual) if actual else 0.0
        rows.append({"id": test["id"], "query": test["query"], "expected": test["expected"], "actual": actual, "recall_at_5": recall, "source_precision": precision, "latency_ms": round(elapsed, 2), "memory_packet_tokens": result["token_estimate"]})
        latencies.append(elapsed); recalls.append(recall); precisions.append(precision); packet_tokens.append(result["token_estimate"])
    ordered = sorted(latencies)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * .95) - 1))
    return {
        "corpus_version": corpus["corpus_version"], "user": user["username"], "queries": len(rows),
        "recall_at_5": round(statistics.mean(recalls), 4), "source_precision": round(statistics.mean(precisions), 4),
        "latency_ms": {"mean": round(statistics.mean(latencies), 2), "p50": round(statistics.median(latencies), 2), "p95": round(ordered[p95_index], 2)},
        "memory_packet_tokens": {"mean": round(statistics.mean(packet_tokens), 1), "max": max(packet_tokens)},
        "note": "This measures local FTS5 retrieval and selected Memory Packet input tokens. It deliberately does not call a paid/provider AI synthesis model.",
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure Nodecast local retrieval quality.")
    parser.add_argument("--username", required=True)
    print(json.dumps(evaluate(parser.parse_args().username), ensure_ascii=False, indent=2))
