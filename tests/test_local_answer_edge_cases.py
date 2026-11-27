"""Offline regression tests for local inference error and evidence contracts."""

import io
import json
from urllib.error import HTTPError, URLError

import pytest

from os29 import local_answer as la
from os29.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "edge.db")


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"query": " "}, "question"),
        ({"query": "x" * (la.MAX_QUERY_CHARS + 1)}, "question cannot"),
        ({"limit": True}, "limit"),
        ({"limit": 7}, "limit"),
        ({"timeout_seconds": 0}, "timeout"),
        ({"num_ctx": 511}, "num_ctx"),
        ({"num_predict": 15}, "num_predict"),
        ({"ollama_url": ""}, "non-empty loopback"),
        ({"model": "bad model"}, "Model name"),
        ({"retrieval_query": "x" * (la.MAX_QUERY_CHARS + 1)}, "retrieval_query"),
    ],
)
def test_rejects_invalid_input_before_network(store, monkeypatch, kwargs, match):
    def unexpected(*a, **k):
        pytest.fail("Network must not be used for invalid input")

    monkeypatch.setattr(la, "urlopen", unexpected)
    with pytest.raises(ValueError, match=match):
        la.answer_from_memory(store, **({"query": "checkpoint"} | kwargs))


@pytest.mark.parametrize(
    "raw,match",
    [
        (b"x" * (la.MAX_RESPONSE_BYTES + 1), "response limit"),
        (b"{", "invalid JSON"),
        (b"\xff", "invalid JSON"),
        (b"[]", "text response"),
        (b'{"response": 1}', "text response"),
        (b'{"response": " "}', "empty"),
        (json.dumps({"response": "x" * 12001}).encode(), "text limit"),
    ],
    ids=["oversized", "bad-json", "bad-utf8", "array", "not-text", "empty", "long-answer"],
)
def test_response_limits(monkeypatch, raw, match):
    monkeypatch.setattr(la, "urlopen", lambda *a, **k: io.BytesIO(raw))
    with pytest.raises(ValueError, match=match):
        la._call_ollama(
            url=la.DEFAULT_OLLAMA_URL,
            model=la.DEFAULT_MODEL,
            system="system",
            prompt="prompt",
            timeout_seconds=1,
            num_ctx=512,
            num_predict=16,
            format_schema={},
        )


@pytest.mark.parametrize(
    "error,match",
    [
        (HTTPError("http://localhost:11434", 503, "unavailable", {}, None), "HTTP 503"),
        (URLError("synthetic"), "URLError"),
        (TimeoutError("synthetic"), "TimeoutError"),
        (OSError("synthetic"), "OSError"),
    ],
)
def test_network_errors_are_bounded(monkeypatch, error, match):
    def fail(*a, **k):
        raise error

    monkeypatch.setattr(la, "urlopen", fail)
    with pytest.raises(ValueError, match=match) as caught:
        la._call_ollama(
            url=la.DEFAULT_OLLAMA_URL,
            model=la.DEFAULT_MODEL,
            system="system",
            prompt="private synthetic prompt",
            timeout_seconds=1,
            num_ctx=512,
            num_predict=16,
            format_schema={},
        )
    assert "private synthetic prompt" not in str(caught.value)


def test_query_and_window_fallbacks():
    assert la._derive_retrieval_query("What is the") == "What is the"
    assert la._select_evidence_window("abcdefgh", "a", 4) == "abcd"
    assert la._select_evidence_window("abc", "query", 4) == "abc"
    assert la._validate_ollama_url(" http://localhost:11434/ ") == "http://localhost:11434"


def _seed(store):
    with store._connect() as conn:
        for key, body in [
            ("blank", " "),
            ("candidate", "unapproved"),
            ("good", "checkpoint evidence"),
            ("next", "second evidence"),
        ]:
            conn.execute(
                "INSERT INTO memory_documents VALUES (?,?,?,?,?,?,?,?,?)",
                (key, "event", key, key, body, "observed", "now", "{}", key),
            )
    return [
        {
            "doc_id": key,
            "source_type": "event",
            "source_ref": key,
            "title": key,
            "trust_status": status,
        }
        for key, status in [
            ("missing", "observed"),
            ("candidate", "candidate"),
            ("blank", "observed"),
            ("good", "observed"),
            ("next", "observed"),
        ]
    ]


def test_evidence_skip_and_budget(store):
    rows = _seed(store)
    assert la._load_evidence_bodies(store, [{}]) == []
    assert la._load_evidence_bodies(store, rows, context_budget=0) == []
    result = la._load_evidence_bodies(store, rows, context_budget=10)
    assert len(result) == 1
    assert result[0]["doc_id"] == "good"
    assert result[0]["citation"] == "E1"
    assert len(result[0]["text"]) <= 10


@pytest.fixture
def seeded(store, monkeypatch):
    rows = _seed(store)
    monkeypatch.setattr(
        la,
        "search_memory",
        lambda *a, **k: {
            "backend": "sqlite_fts5",
            "retrieval_mode": "lexical_bm25",
            "indexed_documents": len(rows),
            "results": rows,
        },
    )
    return store


@pytest.mark.parametrize(
    "raw,match",
    [
        ("not-json", "structured-answer JSON"),
        ("[]", "structured-answer contract"),
        (
            '{"answer":"ok","citations":[1],"insufficient_evidence":false}',
            "structured-answer contract",
        ),
        ('{"answer":" ","citations":[],"insufficient_evidence":false}', "empty or oversized"),
    ],
)
def test_structured_answer_rejections(seeded, monkeypatch, raw, match):
    monkeypatch.setattr(la, "_call_ollama", lambda **k: {"answer": raw, "model": "test"})
    with pytest.raises(ValueError, match=match):
        la.answer_from_memory(seeded, "checkpoint")


def test_model_explicitly_reports_insufficient_evidence(seeded, monkeypatch):
    monkeypatch.setattr(
        la,
        "_call_ollama",
        lambda **k: {
            "model": "test",
            "answer": json.dumps(
                {"answer": "Missing data", "citations": [], "insufficient_evidence": True}
            ),
        },
    )
    result = la.answer_from_memory(seeded, "checkpoint")
    assert result["answer_status"] == "evidence_insufficient"
    assert result["model_called"] is True


def test_prompt_budget_rejects_oversized_evidence(seeded, monkeypatch):
    monkeypatch.setattr(
        la,
        "_load_evidence_bodies",
        lambda *a, **k: [
            {
                "citation": "E1",
                "doc_id": "good",
                "source_type": "event",
                "source_ref": "good",
                "title": "good",
                "trust_status": "observed",
                "text": "x" * 14000,
            }
        ],
    )
    monkeypatch.setattr(la, "_call_ollama", lambda **k: pytest.fail("Budget bypass"))
    with pytest.raises(ValueError, match="fixed context budget"):
        la.answer_from_memory(seeded, "checkpoint")
