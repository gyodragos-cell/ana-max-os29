#!/usr/bin/env python3
"""
OS29 Example 04 — Lexical FTS5 vs Hybrid Retrieval + Row-Wise L2 Normalization
Demonstrates FTS5/BM25 baseline, DeterministicHashEmbedder hybrid RRF fusion,
and rejection of invalid zero/NaN/Inf vectors.

Run: python examples/04_custom_retriever_hybrid.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from os29.models import TraceEvent  # noqa: E402
from os29.retrieval import search_memory  # noqa: E402
from os29.retrieval_vector import (  # noqa: E402
    DeterministicHashEmbedder,
    normalize_row,
    rank_vectors,
    search_memory_hybrid,
)
from os29.store import Store  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "hybrid.db")
        docs = [
            ("trace-01", "sqlite wal busy timeout multi-process checkpoint"),
            ("trace-02", "mcp stdio jsonrpc schema validation policy guard"),
            ("trace-03", "sha256 work unit hash chain external anchor audit"),
        ]
        for trace_id, text in docs:
            store.record_event(
                TraceEvent(
                    trace_id=trace_id,
                    source="example",
                    component="retriever",
                    kind="diagnostic",
                    action=text,
                    outcome="observed",
                    attributes={"topic": trace_id},
                )
            )

        lexical = search_memory(store, "sqlite checkpoint", limit=5, include_candidates=True)
        backend = DeterministicHashEmbedder(dimensions=128)
        hybrid = search_memory_hybrid(
            store,
            "sqlite checkpoint",
            backend,
            limit=5,
            vector_weight=0.5,
            include_candidates=True,
        )

        unit = normalize_row([3.0, 4.0])
        assert abs(unit[0] - 0.6) < 1e-9 and abs(unit[1] - 0.8) < 1e-9

        rejected: list[str] = []
        for bad in ([0.0, 0.0], [float("nan"), 1.0], [float("inf"), 0.0]):
            try:
                normalize_row(bad)
            except ValueError as exc:
                rejected.append(str(exc))
        assert len(rejected) == 3

        ranked = rank_vectors([1.0, 0.0], [("same", [2.0, 0.0]), ("ortho", [0.0, 1.0])])
        assert ranked[0][0] == "same" and ranked[1][0] == "ortho"

        output = {
            "lexical_top": lexical["results"][0]["source_ref"] if lexical["results"] else None,
            "hybrid_top": hybrid["results"][0]["source_ref"] if hybrid["results"] else None,
            "hybrid_rrf_score": round(hybrid["results"][0]["rrf_score"], 6)
            if hybrid["results"]
            else None,
            "normalized_3_4": [round(x, 4) for x in unit],
            "invalid_vectors_rejected": rejected,
        }
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Run verification examples without Python -O")
    main()
