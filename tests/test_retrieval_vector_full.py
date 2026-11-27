# FILE: tests/test_retrieval_vector_full.py
import math

import pytest

from os29.models import TraceEvent
from os29.retrieval_vector import (
    DeterministicHashEmbedder,
    normalize_row,
    rank_vectors,
    search_memory_hybrid,
)
from os29.store import Store


def test_normalize():
    assert normalize_row([3.0, 4.0]) == pytest.approx((0.6, 0.8))
    assert math.hypot(*normalize_row([1e308, 1e308])) == pytest.approx(1)
    assert normalize_row([3e-300, 4e-300]) == pytest.approx((0.6, 0.8))


@pytest.mark.parametrize(
    "row,reason",
    [
        ([0.0, 0.0], "zero-length"),
        ([float("nan")], "finite"),
        ([float("inf")], "finite"),
        ([-float("inf")], "finite"),
        ([], "dimension"),
        ([1] * 4097, "dimension"),
        ([True], "real numbers"),
        (["1"], "real numbers"),
        ([10**400], "finite"),
    ],
)
def test_invalid_vectors(row, reason):
    with pytest.raises(ValueError, match=reason) as error:
        normalize_row(row)
    assert reason in str(error.value)


def test_rank_five():
    candidates = [
        ("orthogonal", [0, 1]),
        ("opposite", [-1, 0]),
        ("same", [2, 0]),
        ("partial", [3, 4]),
        ("negative", [-3, 4]),
    ]
    result = rank_vectors([1, 0], candidates)
    assert [key for key, _ in result] == ["same", "partial", "orthogonal", "negative", "opposite"]
    assert [score for _, score in result] == pytest.approx([1, 0.6, 0, -0.6, -1])
    assert rank_vectors([1, 0], list(reversed(candidates))) == result


def test_empty_single_and_orthogonal():
    assert rank_vectors([1, 0], []) == []
    assert rank_vectors([3, 4], [("same", [3, 4])]) == [("same", pytest.approx(1))]
    assert rank_vectors([1, 0], [("other", [0, 1])]) == [("other", 0.0)]


def test_top_k_deterministic_ties():
    documents = [(f"d{i}", [1, 0]) for i in reversed(range(10))]
    expected = [("d0", 1.0), ("d1", 1.0), ("d2", 1.0)]
    assert rank_vectors([1, 0], documents, top_k=3) == expected
    assert rank_vectors([1, 0], documents, top_k=3) == expected


@pytest.mark.parametrize("k", [0, -1, 1001, True, 1.5])
def test_invalid_top_k(k):
    with pytest.raises(ValueError, match="top_k") as error:
        rank_vectors([1], [], top_k=k)
    assert "top_k" in str(error.value)


@pytest.mark.parametrize(
    "docs,reason",
    [
        ([(str(i), [1]) for i in range(1001)], "candidate limit"),
        ([("", [1])], "unique"),
        ([(1, [1])], "unique"),
        ([("a", [1]), ("a", [1])], "unique"),
        ([("a", [1, 2])], "dimensions"),
    ],
)
def test_invalid_candidates(docs, reason):
    with pytest.raises(ValueError, match=reason) as error:
        rank_vectors([1], docs)
    assert reason in str(error.value)


@pytest.mark.parametrize("dims", [7, 4097, True, 8.0])
def test_bad_embedder_dimensions(dims):
    with pytest.raises(ValueError, match="dimensions") as error:
        DeterministicHashEmbedder(dims).embed(["test"])
    assert "dimensions" in str(error.value)


def test_embedder():
    backend = DeterministicHashEmbedder(8)
    a, b = backend.embed(["HELLO hello", "hello"])
    assert sum(a) == 2 and sum(b) == 1
    assert a == [2 * v for v in b]
    assert backend.embed([]) == []
    with pytest.raises(ValueError, match="zero-length") as error:
        backend.embed(["___!!!"])
    assert "zero-length" in str(error.value)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "memory.db")


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"limit": 0}, "limit"),
        ({"limit": True}, "limit"),
        ({"vector_weight": -0.1}, "vector_weight"),
        ({"vector_weight": float("nan")}, "vector_weight"),
        ({"vector_weight": True}, "vector_weight"),
        ({"max_documents": 0}, "max_documents"),
        ({"max_documents": 1001}, "max_documents"),
    ],
)
def test_hybrid_invalid_options(store, kwargs, reason):
    with pytest.raises(ValueError, match=reason) as error:
        search_memory_hybrid(store, "cosine", DeterministicHashEmbedder(), **kwargs)
    assert reason in str(error.value)


def test_hybrid_empty(store):
    result = search_memory_hybrid(store, "cosine", DeterministicHashEmbedder())
    assert result["results"] == []
    assert result["result_count"] == result["vector_candidates"] == 0


def test_hybrid_weight_and_scope(store):
    for title in ("cosine normalization", "sqlite checkpoint"):
        store.record_event(
            TraceEvent(
                trace_id=title,
                source="test",
                component="test",
                kind="diagnostic",
                action=title,
                outcome="observed",
            )
        )
    backend = DeterministicHashEmbedder()
    result = search_memory_hybrid(store, "cosine", backend, vector_weight=0)
    assert result["result_count"] == 1
    assert result["vector_candidates"] == 2
    assert result["results"][0]["lexical_rank"] == 1
    assert result["results"][0]["rrf_score"] == pytest.approx(1 / 61)
    result = search_memory_hybrid(
        store, "cosine", backend, vector_weight=1, include_candidates=True, source_types=["event"]
    )
    assert result["result_count"] == 2
    assert all(row["source_type"] == "event" for row in result["results"])
    assert result["results"][0]["rrf_score"] == pytest.approx(1 / 61)
