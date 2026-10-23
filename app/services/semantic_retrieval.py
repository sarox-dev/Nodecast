"""Optional local semantic retrieval and deterministic candidate fusion.

Embeddings are derived indexes.  Providers must be explicitly registered and
must not download models as a side effect of a query.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Callable, Iterable


Embedder = Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class EmbeddingProvider:
    provider: str
    model: str
    revision: str
    dimensions: int
    embed: Embedder


_providers: dict[tuple[str, str], EmbeddingProvider] = {}


def register_embedding_provider(provider: EmbeddingProvider) -> None:
    if not provider.provider or not provider.model or provider.dimensions < 1:
        raise ValueError("Invalid embedding provider identity")
    _providers[(provider.provider, provider.model)] = provider


def unregister_embedding_provider(provider: str, model: str) -> None:
    _providers.pop((provider, model), None)


def get_embedding_provider(provider: str, model: str) -> EmbeddingProvider | None:
    return _providers.get((provider, model))


def pack_vector(values: Iterable[float]) -> bytes:
    vector = [float(value) for value in values]
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("Embedding must contain finite values")
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack_vector(payload: bytes, dimensions: int) -> list[float]:
    if dimensions < 1 or len(payload) != dimensions * 4:
        raise ValueError("Embedding dimensions do not match stored bytes")
    return list(struct.unpack(f"<{dimensions}f", payload))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def reciprocal_rank_fusion(
    lexical: list[dict], semantic: list[dict], limit: int, rank_constant: int = 60
) -> list[dict]:
    """Fuse independent rankings; similarity remains a signal, never evidence."""
    by_id: dict[str, dict] = {}
    scores: dict[str, float] = {}
    signals: dict[str, set[str]] = {}
    for signal, rows in (("lexical", lexical), ("semantic", semantic)):
        for rank, row in enumerate(rows, start=1):
            atomic_id = row["id"]
            by_id.setdefault(atomic_id, dict(row))
            scores[atomic_id] = scores.get(atomic_id, 0.0) + 1.0 / (rank_constant + rank)
            signals.setdefault(atomic_id, set()).add(signal)
    ordered = sorted(by_id, key=lambda item: (-scores[item], item))
    result = []
    for atomic_id in ordered[:limit]:
        item = by_id[atomic_id]
        item["retrieval_score"] = scores[atomic_id]
        item["retrieval_signals"] = sorted(signals[atomic_id])
        result.append(item)
    return result
