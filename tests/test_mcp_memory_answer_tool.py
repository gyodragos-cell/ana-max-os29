from __future__ import annotations

import json

import os29.mcp_stdio as mcp_stdio


def _call(arguments):
    return mcp_stdio.handle({
        "jsonrpc": "2.0",
        "id": 41,
        "method": "tools/call",
        "params": {"name": "os29_memory_answer", "arguments": arguments},
    })


def _decode(response):
    result = response["result"]
    return result, json.loads(result["content"][0]["text"])


def test_memory_answer_schema_is_bounded_and_has_no_endpoint_override():
    tool = next(item for item in mcp_stdio.schemas() if item["name"] == "os29_memory_answer")
    schema = tool["inputSchema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["query"]
    props = schema["properties"]
    assert props["query"]["maxLength"] == 2000
    assert props["limit"]["minimum"] == 1 and props["limit"]["maximum"] == 6
    assert props["timeout_seconds"]["minimum"] == 1 and props["timeout_seconds"]["maximum"] == 90
    assert props["num_ctx"]["minimum"] == 512 and props["num_ctx"]["maximum"] == 4096
    assert props["num_predict"]["minimum"] == 16 and props["num_predict"]["maximum"] == 512
    assert "ollama_url" not in props
    assert "source_types" in props and "items" in props["source_types"]


def test_memory_answer_dispatch_uses_fixed_endpoint_and_allowed_bounded_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_stdio, "DB_PATH", tmp_path / "dispatch.db")
    captured = {}

    def fake_answer(store, query, **kwargs):
        captured["db_path"] = str(store.db_path)
        captured["query"] = query
        captured["kwargs"] = kwargs
        return {
            "answer_status": "grounded",
            "answer": "The approved evidence supports this answer [E1].",
            "model_called": True,
            "cited_ids": ["E1"],
            "invalid_citation_ids": [],
        }

    monkeypatch.setattr(mcp_stdio, "answer_from_memory", fake_answer)
    response = _call({
        "query": "What changed?",
        "model": "qwen2.5-coder:3b",
        "limit": 2,
        "timeout_seconds": 5,
        "num_ctx": 1024,
        "num_predict": 64,
        "source_types": ["document"],
        "retrieval_query": "specific change",
    })
    result, payload = _decode(response)
    assert result["isError"] is False
    assert payload["answer_status"] == "grounded"
    assert captured["query"] == "What changed?"
    assert captured["kwargs"] == {
        "model": "qwen2.5-coder:3b",
        "limit": 2,
        "timeout_seconds": 5,
        "num_ctx": 1024,
        "num_predict": 64,
        "source_types": ["document"],
        "retrieval_query": "specific change",
    }


def test_memory_answer_rejects_caller_endpoint_override_without_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_stdio, "DB_PATH", tmp_path / "endpoint-guard.db")
    called = False

    def forbidden_call(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("The model helper must not be reached.")

    monkeypatch.setattr(mcp_stdio, "answer_from_memory", forbidden_call)
    response = _call({"query": "What changed?", "ollama_url": "https://example.invalid:11434"})
    result, payload = _decode(response)
    assert result["isError"] is True
    assert "unsupported os29_memory_answer arguments: ollama_url" in payload["error"]
    assert called is False


def test_memory_answer_invalid_citations_are_mcp_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_stdio, "DB_PATH", tmp_path / "invalid-citation.db")
    monkeypatch.setattr(mcp_stdio, "answer_from_memory", lambda *_args, **_kwargs: {
        "answer_status": "invalid_citations",
        "answer": "Unverified answer.",
        "cited_ids": [],
        "invalid_citation_ids": ["E99"],
    })
    response = _call({"query": "What changed?"})
    result, payload = _decode(response)
    assert result["isError"] is True
    assert payload["answer_status"] == "invalid_citations"
    assert payload["invalid_citation_ids"] == ["E99"]


def test_insufficient_evidence_is_explicit_and_does_not_masquerade_as_grounded(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_stdio, "DB_PATH", tmp_path / "insufficient.db")
    monkeypatch.setattr(mcp_stdio, "answer_from_memory", lambda *_args, **_kwargs: {
        "answer_status": "evidence_insufficient",
        "answer": "No approved evidence matched. No model call was made.",
        "model_called": False,
        "retrieval": {"result_count": 0},
        "citations": {},
    })
    response = _call({"query": "Question without evidence"})
    result, payload = _decode(response)
    assert result["isError"] is False
    assert payload["answer_status"] == "evidence_insufficient"
    assert payload["model_called"] is False
