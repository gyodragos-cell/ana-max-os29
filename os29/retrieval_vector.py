"""Optional local embedding interface and bounded hybrid rank fusion.

The default OS29 search remains SQLite FTS5/BM25. The included hash feature
encoder is deterministic, lexical, and explicitly not a semantic AI model.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .retrieval import search_memory
from .store import Store


class EmbeddingBackend(Protocol):
    @property
    def name(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one finite, nonzero vector per input text."""
        ...


def normalize_row(row: Sequence[float]) -> tuple[float, ...]:
    if not row or len(row) > 4096:
        raise ValueError("vector dimension must be between 1 and 4096")
    if any(type(value) not in {float, int} for value in row):
        raise ValueError("vector values must be real numbers")
    try:
        values = tuple(float(value) for value in row)
    except (ValueError, OverflowError) as exc:
        raise ValueError("vector values must be finite") from exc
    if not all(math.isfinite(value) for value in values):
        raise ValueError("vector values must be finite")
    scale = max(abs(value) for value in values)
    if scale == 0:
        raise ValueError("zero-length vector")
    scaled = tuple(value / scale for value in values)
    norm = math.hypot(*scaled)
    return tuple(value / norm for value in scaled)


def rank_vectors(
    query: Sequence[float],
    documents: Sequence[tuple[str, Sequence[float]]],
    *,
    top_k: int = 10,
) -> list[tuple[str, float]]:
    if type(top_k) is not int or not 1 <= top_k <= 1000:
        raise ValueError("top_k must be between 1 and 1000")
    if len(documents) > 1000:
        raise ValueError("vector candidate limit exceeded")
    normalized_query = normalize_row(query)
    ranked: list[tuple[str, float]] = []
    seen: set[str] = set()
    for identifier, row in documents:
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("document IDs must be unique nonempty strings")
        seen.add(identifier)
        if len(row) != len(normalized_query):
            raise ValueError("vector dimensions do not match")
        # Normalize each document independently before taking the dot product.
        normalized_document = normalize_row(row)
        score = math.fsum(a * b for a, b in zip(normalized_query, normalized_document))
        ranked.append((identifier, max(-1.0, min(1.0, score))))
    return sorted(ranked, key=lambda item: (-item[1], item[0]))[:top_k]


@dataclass(frozen=True)
class DeterministicHashEmbedder:
    dimensions: int = 128
    name: str = "deterministic_token_hash_v1"

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if type(self.dimensions) is not int or not 8 <= self.dimensions <= 4096:
            raise ValueError("embedding dimensions must be between 8 and 4096")
        output: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:8], "big") % self.dimensions
                vector[index] += 1.0
            if not any(vector):
                raise ValueError("text produced a zero-length embedding")
            output.append(vector)
        return output


def search_memory_hybrid(
    store: Store,
    query: str,
    backend: EmbeddingBackend,
    *,
    limit: int = 10,
    vector_weight: float = 0.5,
    max_documents: int = 1000,
    include_candidates: bool = False,
    source_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if (
        type(vector_weight) not in {float, int}
        or not math.isfinite(vector_weight)
        or not 0 <= vector_weight <= 1
    ):
        raise ValueError("vector_weight must be between 0 and 1")
    if type(max_documents) is not int or not 1 <= max_documents <= 1000:
        raise ValueError("max_documents must be between 1 and 1000")
    lexical = search_memory(
        store,
        query,
        limit=min(100, max(limit * 3, limit)),
        include_candidates=include_candidates,
        source_types=source_types,
        refresh=not store.read_only,
    )
    conditions = (
        ["trust_status != 'rejected'"]
        if include_candidates
        else ["trust_status NOT IN ('candidate', 'rejected')"]
    )
    params: list[Any] = []
    if source_types:
        conditions.append(
            "source_type IN (" + ",".join("?" for _ in source_types) + ")"
        )
        params.extend(source_types)
    with store._connect() as connection:
        rows = connection.execute(
            "SELECT doc_id, source_type, source_ref, title, body, trust_status FROM memory_documents "
            "WHERE " + " AND ".join(conditions) + " ORDER BY doc_id LIMIT ?",
            params + [max_documents + 1],
        ).fetchall()
    if len(rows) > max_documents:
        raise ValueError(
            "vector corpus exceeds configured limit; use FTS5 or a smaller scope"
        )
    if not rows:
        return {
            "backend": backend.name,
            "retrieval_mode": "hybrid_rrf",
            "result_count": 0,
            "vector_candidates": 0,
            "results": [],
        }
    texts = [query] + [row["title"] + "\n" + row["body"] for row in rows]
    vectors = backend.embed(texts)
    if len(vectors) != len(texts):
        raise ValueError("embedding backend returned wrong vector count")
    vector_ranked = rank_vectors(
        vectors[0],
        [(row["doc_id"], vector) for row, vector in zip(rows, vectors[1:])],
        top_k=len(rows),
    )
    vector_ranks = {
        identifier: (rank, score)
        for rank, (identifier, score) in enumerate(vector_ranked, 1)
    }
    lexical_ranks = {
        item["doc_id"]: rank for rank, item in enumerate(lexical["results"], 1)
    }
    results: list[dict[str, Any]] = []
    for row in rows:
        identifier = row["doc_id"]
        lex_rank = lexical_ranks.get(identifier)
        vec_rank, score = vector_ranks[identifier]
        fused = (1 - vector_weight) / (60 + lex_rank) if lex_rank else 0.0
        fused += vector_weight / (60 + vec_rank)
        if fused > 0:
            results.append(
                {
                    "doc_id": identifier,
                    "source_type": row["source_type"],
                    "source_ref": row["source_ref"],
                    "title": row["title"],
                    "trust_status": row["trust_status"],
                    "lexical_rank": lex_rank,
                    "vector_rank": vec_rank,
                    "cosine_score": score,
                    "rrf_score": fused,
                }
            )
    results.sort(key=lambda item: (-item["rrf_score"], item["doc_id"]))
    return {
        "backend": backend.name,
        "retrieval_mode": "hybrid_rrf",
        "vector_candidates": len(rows),
        "result_count": min(limit, len(results)),
        "results": results[:limit],
        "vector_weight": vector_weight,
    }
