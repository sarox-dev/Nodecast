#!/usr/bin/env python3
"""Run the deterministic multilingual retrieval baseline in an isolated temp DB."""

import argparse
import json
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services import database
from app.services.database import enrich_atomics_with_sources, search_atomics
from app.services.memory_retrieval import _diverse, detect_intent


DEFAULT_CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "multilingual_recall_corpus.json"


def load_corpus(path: Path = DEFAULT_CORPUS_PATH) -> dict:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    capture_ids = [item["id"] for item in corpus["captures"]]
    query_ids = [item["id"] for item in corpus["queries"]]
    if len(capture_ids) != len(set(capture_ids)) or len(query_ids) != len(set(query_ids)):
        raise ValueError("Corpus capture and query IDs must be unique")
    return corpus


def configure_temp_database(root: Path) -> None:
    database.CONTENTS_DIR = root
    database.USERS_DB_PATH = root / "users.db"
    database.USERS_DATA_DIR = root / "users"


def seed_corpus(corpus: dict) -> tuple[str, dict[str, str], dict[str, dict]]:
    user_id = database.create_user_in_db("multilingual-eval", "not-a-login-hash", False)
    database.init_user_db(user_id)
    evidence_ids = {}
    evidence_by_id = {}

    for capture in corpus["captures"]:
        database.insert_capture_ref(
            user_id,
            capture["id"],
            capture.get("capture_type", "snippet"),
            capture["url"],
            capture["title"],
            capture["site"],
            "2026-10-22T00:00:00Z",
            "2026-10-22T00:00:00Z",
            [capture["language"], capture["script"]],
            "multilingual retrieval evaluation",
            "",
        )
        if capture.get("indexed", True) is False:
            continue
        source_text = "\n\n".join(item["text"] for item in capture.get("evidence", []))
        cursor = 0
        for position, item in enumerate(capture.get("evidence", [])):
            start = source_text.index(item["text"], cursor)
            end = start + len(item["text"])
            cursor = end
            properties = {
                "evaluation_key": item["key"],
                "dimension": item["dimension"],
                "provenance_version": 1,
                "source_span": {"capture_id": capture["id"], "kind": "paragraph", "start": start, "end": end},
                "analysis": {"language": capture["language"], "scripts": [capture["script"]]},
                "evaluation_source_text": source_text,
            }
            atomic_id = database.insert_atomic(
                user_id,
                "text",
                item["text"],
                properties=properties,
                source_id=capture["id"],
                extracted_by="multilingual-eval-fixture-v1",
                position=position,
                context_header=capture["title"],
            )
            evidence_ids[item["key"]] = atomic_id
            evidence_by_id[atomic_id] = {"key": item["key"], "capture_id": capture["id"], **item, "properties": properties}
    return user_id, evidence_ids, evidence_by_id


def _source_span_is_faithful(item: dict) -> bool:
    properties = item.get("properties") or {}
    span = properties.get("source_span") or {}
    source_text = properties.get("evaluation_source_text", "")
    start, end = span.get("start"), span.get("end")
    return (
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start <= end <= len(source_text)
        and source_text[start:end] == item.get("content", "")
        and span.get("capture_id") == item.get("source_id")
    )


def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 4) if values else 0.0


def evaluate_corpus(corpus: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="nodecast-multilingual-eval-") as tmp:
        configure_temp_database(Path(tmp))
        user_id, evidence_ids, _evidence_by_id = seed_corpus(corpus)
        rows = []
        latencies = []

        for query in corpus["queries"]:
            started = time.perf_counter()
            raw = enrich_atomics_with_sources(user_id, search_atomics(user_id, query["query"], limit=30))
            candidates = [item for item in raw if item.get("role", "evidence") == "evidence" and item.get("status", "ready") != "rejected"]
            ranked = _diverse(candidates, 10)
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)

            actual_sources = [item["source_id"] for item in ranked]
            actual_evidence = [item["id"] for item in ranked]
            expected_sources = set(query["expected_sources"])
            expected_evidence = {evidence_ids[key] for key in query["expected_evidence"]}
            top5_sources = set(actual_sources[:5])
            top10_sources = set(actual_sources[:10])
            top5_evidence = set(actual_evidence[:5])
            top10_evidence = set(actual_evidence[:10])
            forbidden = set(query.get("forbidden_sources", []))
            required_dimensions = set(query.get("required_dimensions", []))
            found_dimensions = {
                (item.get("properties") or {}).get("dimension")
                for item in ranked[:10]
                if (item.get("properties") or {}).get("dimension")
            }
            faithful = [_source_span_is_faithful(item) for item in ranked[:10]]

            source_recall_5 = len(expected_sources & top5_sources) / len(expected_sources) if expected_sources else 1.0
            source_recall_10 = len(expected_sources & top10_sources) / len(expected_sources) if expected_sources else 1.0
            evidence_recall_5 = len(expected_evidence & top5_evidence) / len(expected_evidence) if expected_evidence else 1.0
            evidence_recall_10 = len(expected_evidence & top10_evidence) / len(expected_evidence) if expected_evidence else 1.0
            precision_5 = len(expected_sources & top5_sources) / len(actual_sources[:5]) if actual_sources[:5] else 0.0
            dimension_coverage = len(required_dimensions & found_dimensions) / len(required_dimensions) if required_dimensions else 1.0
            rows.append({
                "id": query["id"],
                "kind": query["kind"],
                "query_language": query["query_language"],
                "query": query["query"],
                "intent": detect_intent(query["query"]),
                "expected_sources": query["expected_sources"],
                "actual_sources": actual_sources,
                "actual_evidence_keys": [(item.get("properties") or {}).get("evaluation_key") for item in ranked],
                "source_recall_at_5": round(source_recall_5, 4),
                "source_recall_at_10": round(source_recall_10, 4),
                "evidence_recall_at_5": round(evidence_recall_5, 4),
                "evidence_recall_at_10": round(evidence_recall_10, 4),
                "source_precision_at_5": round(precision_5, 4),
                "dimension_coverage": round(dimension_coverage, 4),
                "source_span_fidelity": _mean([1.0 if value else 0.0 for value in faithful]) if faithful else 1.0,
                "forbidden_source_hits": sorted(forbidden & top10_sources),
                "expected_current_gap": query.get("expected_current_gap"),
                "latency_ms": round(elapsed_ms, 2),
            })

        by_kind = defaultdict(list)
        for row in rows:
            by_kind[row["kind"]].append(row)
        ordered = sorted(latencies)
        p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
        return {
            "corpus_version": corpus["corpus_version"],
            "captures": len(corpus["captures"]),
            "queries": len(rows),
            "metrics": {
                "source_recall_at_5": _mean([row["source_recall_at_5"] for row in rows]),
                "source_recall_at_10": _mean([row["source_recall_at_10"] for row in rows]),
                "evidence_recall_at_5": _mean([row["evidence_recall_at_5"] for row in rows]),
                "evidence_recall_at_10": _mean([row["evidence_recall_at_10"] for row in rows]),
                "source_precision_at_5": _mean([row["source_precision_at_5"] for row in rows]),
                "dimension_coverage": _mean([row["dimension_coverage"] for row in rows]),
                "source_span_fidelity": _mean([row["source_span_fidelity"] for row in rows]),
                "cross_language_source_recall_at_5": _mean([row["source_recall_at_5"] for row in by_kind["cross_language"]]),
            },
            "latency_ms": {
                "mean": round(statistics.mean(latencies), 2),
                "p50": round(statistics.median(latencies), 2),
                "p95": round(ordered[p95_index], 2),
            },
            "capabilities": {"lexical": True, "multilingual_embeddings": False, "external_ai_calls": False},
            "note": "Baseline-only measurement of current FTS5 retrieval in an isolated temporary database; expected failures do not make the command fail.",
            "results": rows,
        }


def evaluate(path: Path = DEFAULT_CORPUS_PATH) -> dict:
    return evaluate_corpus(load_corpus(path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure the current multilingual retrieval baseline without touching user data.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.corpus)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
