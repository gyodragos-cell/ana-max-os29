"""Offline, deterministic vector and hybrid retrieval invariants."""

from __future__ import annotations

import math

import pytest

from os29.models import TraceEvent
from os29.retrieval import refresh_memory_index, search_memory
from os29.retrieval_vector import (
    DeterministicHashEmbedder,
    normalize_row,
    rank_vectors,
    search_memory_hybrid,
)
from os29.store import Store


def test_row_normalization_fixes_magnitude_ranking_and_scale_invariance():
    query = (1.0, 0.0)
    documents = [("inflated", (20.0, 40.0)), ("best", (0.8, 0.6))]
    result = rank_vectors(query, documents, top_k=2)
    assert result[0] == ("best", pytest.approx(0.8))
    for scale in (1e-200, 1e-3, 10.0, 1e200):
        scaled = [(key, tuple(value * scale for value in row)) for key, row in documents]
        again = rank_vectors(tuple(v * scale for v in query), scaled, top_k=2)
        assert [key for key, _ in again] == [key for key, _ in result]
        assert [score for _, score in again] == pytest.approx([score for _, score in result])
    assert math.hypot(*normalize_row((1e308, 1e308))) == pytest.approx(1.0)


@pytest.mark.parametrize("bad", [[], [0.0, 0.0], [float("nan")], [float("inf")], [True]])
def test_invalid_vectors_rejected(bad):
    with pytest.raises(ValueError):
        normalize_row(bad)


def test_duplicate_dimension_and_tie_validation():
    with pytest.raises(ValueError, match="dimensions"):
        rank_vectors([1.0], [("a", [1.0, 2.0])])
    with pytest.raises(ValueError, match="unique"):
        rank_vectors([1.0], [("a", [1.0]), ("a", [2.0])])
    assert rank_vectors([1.0], [("z", [2.0]), ("a", [1.0])]) == [("a", 1.0), ("z", 1.0)]


def seed(store):
    for title in ("cosine normalization", "sqlite durable checkpoint", "mcp protocol"):
        store.record_event(
            TraceEvent(
                trace_id=title,
                source="synthetic",
                component="example",
                kind="diagnostic",
                action=title,
                outcome="observed",
            )
        )


def test_hybrid_uses_real_fts_and_optional_deterministic_backend(tmp_path):
    store = Store(tmp_path / "memory.db")
    seed(store)
    base = search_memory(store, "cosine normalization")
    assert base["backend"] == "sqlite_fts5"
    assert base["result_count"] == 1
    backend = DeterministicHashEmbedder(128)
    assert backend.embed(["cosine normalization"]) == backend.embed(["cosine normalization"])
    result = search_memory_hybrid(store, "cosine normalization", backend, limit=3)
    assert result["vector_candidates"] == 3
    assert result["results"][0]["doc_id"] == base["results"][0]["doc_id"]
    assert all(-1 <= row["cosine_score"] <= 1 for row in result["results"])
    assert search_memory_hybrid(store, "cosine normalization", backend, limit=3) == result
    with pytest.raises(ValueError, match="corpus exceeds"):
        search_memory_hybrid(store, "cosine normalization", backend, max_documents=2)


def test_backend_is_pluggable_and_validates_count(tmp_path):
    store = Store(tmp_path / "memory.db")
    seed(store)

    class BrokenBackend:
        name = "broken"

        def embed(self, texts):
            return [[1.0]]

    with pytest.raises(ValueError, match="wrong vector count"):
        search_memory_hybrid(store, "sqlite", BrokenBackend())


def test_read_only_search_uses_existing_index_without_writing(tmp_path):
    database = tmp_path / "memory.db"
    store = Store(database)
    seed(store)
    refresh_memory_index(store)
    readonly = Store(database, read_only=True)
    result = search_memory(readonly, "cosine normalization")
    assert result["result_count"] == 1
    assert result["index_refresh"] is None
    assert (
        search_memory_hybrid(readonly, "cosine normalization", DeterministicHashEmbedder())[
            "result_count"
        ]
        == 3
    )
