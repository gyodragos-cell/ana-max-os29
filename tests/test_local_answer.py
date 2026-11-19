from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

import os29.local_answer as local_answer
from os29.cli import build_parser
from os29.local_answer import answer_from_memory
from os29.store import Store


def _store_with_approved_doc(tmp_path: Path, content: str) -> tuple[Store, Path]:
    config_dir = tmp_path / "config"
    docs_dir = tmp_path / "docs"
    config_dir.mkdir(exist_ok=True)
    docs_dir.mkdir(exist_ok=True)
    source = docs_dir / "approved-evidence.md"
    source.write_text(content, encoding="utf-8")
    (config_dir / "memory_sources.json").write_text(
        json.dumps({
            "files": [str(source)],
            "directories": [],
            "limits": {
                "max_file_bytes": 524288,
                "max_total_source_bytes": 8388608,
                "max_files": 200,
            },
        }),
        encoding="utf-8",
    )
    return Store(tmp_path / "os29.db"), source.resolve()


def _response(
    answer: str,
    *,
    citations: list[str] | None = None,
    insufficient_evidence: bool = False,
) -> io.BytesIO:
    structured = {
        "answer": answer,
        "citations": ["E1"] if citations is None else citations,
        "insufficient_evidence": insufficient_evidence,
    }
    return io.BytesIO(json.dumps({
        "response": json.dumps(structured, ensure_ascii=False),
        "total_duration": 123456,
        "prompt_eval_count": 91,
        "eval_count": 14,
    }).encode("utf-8"))


def test_local_answer_uses_approved_evidence_and_validates_citation(tmp_path, monkeypatch):
    secret = "password=fixture-secret-never-send-7d2c"
    store, source = _store_with_approved_doc(
        tmp_path,
        "# Live acceptance\nThe operator-local-full gateway exposes 139 tools. "
        "The bounded acceptance test passed. " + secret,
    )
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _response("The operator-local-full gateway exposes 139 tools.", citations=["E1"])

    monkeypatch.setattr(local_answer, "urlopen", fake_urlopen)
    result = answer_from_memory(
        store,
        "operator-local-full gateway 139 tools",
        model="qwen2.5-coder:3b",
        limit=4,
        timeout_seconds=5,
        num_ctx=1024,
        num_predict=64,
        retrieval_query="operator-local-full gateway 139 tools",
    )

    assert result["answer_status"] == "grounded"
    assert result["cited_ids"] == ["E1"]
    assert result["invalid_citation_ids"] == []
    assert result["citations"]["E1"]["source_ref"] == str(source)
    assert result["retrieval"]["retrieval_mode"] == "lexical_bm25"
    assert result["retrieval"]["semantic_embeddings_enabled"] is False
    assert result["keep_alive_seconds"] == 0
    assert "[E1]" in result["answer"]
    assert result["retrieval"]["retrieval_query"] == "operator-local-full gateway 139 tools"
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert captured["timeout"] == 5
    assert captured["payload"]["model"] == "qwen2.5-coder:3b"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["keep_alive"] == 0
    assert captured["payload"]["format"]["properties"]["citations"]["items"]["enum"] == ["E1"]
    assert captured["payload"]["format"]["required"] == ["answer", "citations", "insufficient_evidence"]
    assert "139 tools" in captured["payload"]["prompt"]
    assert secret not in captured["payload"]["prompt"]
    assert secret not in json.dumps(result, ensure_ascii=False)


def test_local_answer_flags_unknown_citation_for_review(tmp_path, monkeypatch):
    store, _ = _store_with_approved_doc(
        tmp_path,
        "# API evidence\nA local status query returned HTTP 200.",
    )
    monkeypatch.setattr(
        local_answer,
        "urlopen",
        lambda *_args, **_kwargs: _response("The endpoint returned HTTP 200.", citations=["E99"]),
    )

    result = answer_from_memory(
        store,
        "endpoint HTTP 200",
        timeout_seconds=5,
        retrieval_query="endpoint HTTP 200",
    )

    assert result["answer_status"] == "invalid_citations"
    assert result["invalid_citation_ids"] == ["E99"]
    assert result["cited_ids"] == []


def test_local_answer_requires_citations_for_grounded_status(tmp_path, monkeypatch):
    store, _ = _store_with_approved_doc(
        tmp_path,
        "# Evidence\nThe memory index refreshed 650 approved documents.",
    )
    monkeypatch.setattr(
        local_answer,
        "urlopen",
        lambda *_args, **_kwargs: _response(
            "The memory index refreshed 650 documents.", citations=[]
        ),
    )
    result = answer_from_memory(
        store,
        "memory index 650 documents",
        timeout_seconds=5,
        retrieval_query="memory index 650 documents",
    )
    assert result["answer_status"] == "needs_review"
    assert result["cited_ids"] == []


def test_local_answer_reports_insufficient_evidence_without_calling_model(tmp_path, monkeypatch):
    store = Store(tmp_path / "empty.db")
    called = False

    def should_not_call(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("The model must not be called without evidence.")

    monkeypatch.setattr(local_answer, "urlopen", should_not_call)
    result = answer_from_memory(store, "unindexed unusual phrase", timeout_seconds=5)

    assert result["answer_status"] == "evidence_insufficient"
    assert result["model_called"] is False
    assert result["retrieval"]["result_count"] == 0
    assert called is False


def test_local_answer_refuses_non_loopback_model_endpoints(tmp_path, monkeypatch):
    store = Store(tmp_path / "empty.db")

    def should_not_call(*_args, **_kwargs):
        raise AssertionError("The network layer must not be reached for a non-loopback URL.")

    monkeypatch.setattr(local_answer, "urlopen", should_not_call)
    with pytest.raises(ValueError, match="loopback endpoint"):
        answer_from_memory(
            store,
            "any question",
            ollama_url="https://example.com:11434",
            timeout_seconds=5,
        )


def test_memory_answer_cli_is_explicit_and_bounded():
    args = build_parser().parse_args([
        "memory-answer",
        "OS28 gateway tool catalog",
        "--model", "qwen2.5-coder:3b",
        "--limit", "3",
        "--timeout", "10",
        "--num-ctx", "1024",
        "--num-predict", "64",
        "--source-type", "document",
        "--retrieve-query", "gateway 139 tools",
    ])
    assert args.command == "memory-answer"
    assert args.query == "OS28 gateway tool catalog"
    assert args.model == "qwen2.5-coder:3b"
    assert args.limit == 3
    assert args.timeout == 10
    assert args.num_ctx == 1024
    assert args.num_predict == 64
    assert args.source_type == ["document"]
    assert args.retrieve_query == "gateway 139 tools"


def test_local_answer_selects_query_matched_window_from_long_evidence(tmp_path, monkeypatch):
    test_id = "test_local_document_index_preserves_content_past_2000_chars_and_redacts_late_secrets"
    secret = "password=fixture-secret-never-send-context-window-91ea"
    decoy = "UNIQUE_DECOY_START_ONLY_NOT_CONTEXT "
    filler = ("Unrelated older notes about code_search and max_results do not answer this question. " * 75)
    content = (
        "# Mixed evidence\n\n" + decoy + filler
        + "\n\n## Retrieval repair\n"
        + "In os29/retrieval.py, _text now calls redact_value(value, max_length=max_chars). "
        + "Regression test: " + test_id + ". It proves a marker after character 2000 is retrievable "
        + "while a late password-like value remains absent from the memory index. " + secret
    )
    probe = local_answer._select_evidence_window(
        content, f"redact_value max_length=max_chars {test_id}", 2200
    )
    assert decoy not in probe
    assert test_id in probe
    store, _ = _store_with_approved_doc(tmp_path, content)
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _response("The retrieval fix is covered by the long-document redaction regression.", citations=["E1"])

    monkeypatch.setattr(local_answer, "urlopen", fake_urlopen)
    result = answer_from_memory(
        store,
        "What exact change fixes long-document truncation and which test proves it?",
        timeout_seconds=5,
        num_ctx=2048,
        num_predict=128,
        retrieval_query=f"redact_value max_length=max_chars {test_id}",
    )

    prompt = captured["payload"]["prompt"]
    assert result["answer_status"] == "grounded"
    assert "redact_value(value, max_length=max_chars)" in prompt
    assert test_id in prompt
    assert "late password-like value remains absent from the memory index" in prompt
    assert decoy not in prompt
    assert "fixture-secret-never-send-context-window-91ea" not in prompt
    assert "fixture-secret-never-send-context-window-91ea" not in json.dumps(result, ensure_ascii=False)