#!/usr/bin/env python3
"""
OS29 Reproducible Benchmark
Run: python benchmarks/run_benchmark.py
Seed: 42 | Episodes: 500 | Zero external dependencies
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import random
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

SEED = 42
N = 500
random.seed(SEED)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOPICS = [
    "gateway",
    "frida",
    "mcp",
    "sqlite",
    "auth",
    "handoff",
    "checkpoint",
    "recovery",
    "telemetry",
    "capability",
    "evidence",
    "audit",
    "policy",
    "scope",
]


def gen_ep(i):
    t = TOPICS[i % len(TOPICS)]
    return {
        "id": f"ep-{i:04d}",
        "topic": t,
        "text": f"Agent executed {t} operation step={i}. "
        f"trace=os29-bench-{i:04d} outcome={'ok' if i % 3 else 'fail'}.",
        "query": t,
        "rel": f"ep-{i:04d}",
    }


EPS = [gen_ep(i) for i in range(N)]
Q100, EP100 = EPS[:100], EPS[:100]


def pct(arr, p):
    s = sorted(arr)
    idx = max(0, math.ceil(len(s) * p / 100) - 1)
    return round(s[idx], 4)


def measure(name, lats, recall5, mrr, n=100):
    return {
        "method": name,
        "p50_ms": pct(lats, 50),
        "p95_ms": pct(lats, 95),
        "p99_ms": pct(lats, 99),
        "recall_at_5_pct": round(recall5 * 100, 1),
        "mrr_at_5": round(mrr, 4),
    }


def run_dict_like():
    store = {ep["id"]: ep["text"] for ep in EPS}
    lats, hits, rr = [], 0, 0.0
    for ep in EP100:
        t0 = time.perf_counter()
        res = [eid for eid, txt in store.items() if ep["query"].lower() in txt.lower()]
        lats.append((time.perf_counter() - t0) * 1000)
        if ep["rel"] in res[:5]:
            hits += 1
            rr += 1 / (res[:5].index(ep["rel"]) + 1)
    return measure("Baseline-1 (Python dict+LIKE)", lats, hits / 100, rr / 100)


def run_regex():
    pairs = [(ep["id"], ep["text"]) for ep in EPS]
    lats, hits, rr = [], 0, 0.0
    for ep in EP100:
        pat = re.compile(re.escape(ep["query"]), re.I)
        t0 = time.perf_counter()
        res = [eid for eid, txt in pairs if pat.search(txt)]
        lats.append((time.perf_counter() - t0) * 1000)
        if ep["rel"] in res[:5]:
            hits += 1
            rr += 1 / (res[:5].index(ep["rel"]) + 1)
    return measure("Baseline-2 (regex full-scan)", lats, hits / 100, rr / 100)


def run_fts5():
    with tempfile.TemporaryDirectory() as tmp:
        db = sqlite3.connect(os.path.join(tmp, "b.db"))
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("CREATE VIRTUAL TABLE docs USING fts5(id UNINDEXED, text, tokenize='unicode61')")
        db.executemany("INSERT INTO docs VALUES(?,?)", [(ep["id"], ep["text"]) for ep in EPS])
        db.commit()
        lats, hits, rr = [], 0, 0.0
        for ep in EP100:
            t0 = time.perf_counter()
            rows = db.execute(
                "SELECT id FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT 5",
                (ep["query"],),
            ).fetchall()
            lats.append((time.perf_counter() - t0) * 1000)
            ids = [r[0] for r in rows]
            if ep["rel"] in ids:
                hits += 1
            with contextlib.suppress(ValueError):
                rr += 1 / (ids.index(ep["rel"]) + 1)
        db.close()
        return measure("OS29 FTS5/BM25 (WAL)", lats, hits / 100, rr / 100)


def main():
    print(f"OS29 Benchmark  seed={SEED}  N={N}  queries=100")
    print("=" * 62)
    results = [run_dict_like(), run_regex(), run_fts5()]
    for r in results:
        print(f"  {r['method']}")
        print(
            f"    p50={r['p50_ms']}ms  p95={r['p95_ms']}ms  p99={r['p99_ms']}ms  Recall@5={r['recall_at_5_pct']}%  MRR@5={r['mrr_at_5']}"
        )

    # Save JSON
    out = ROOT / "benchmarks" / "results.json"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {"seed": SEED, "n_episodes": N, "n_queries": 100, "results": results},
            f,
            indent=2,
        )
        f.write("\n")

    # Markdown
    hdr = ["Method", "p50 (ms)", "p95 (ms)", "p99 (ms)", "Recall@5 (%)", "MRR@5"]
    sep = "|".join(["---"] * len(hdr))
    rows = ["|".join(hdr), sep]
    for r in results:
        rows.append(
            "|".join(
                [
                    r["method"],
                    str(r["p50_ms"]),
                    str(r["p95_ms"]),
                    str(r["p99_ms"]),
                    str(r["recall_at_5_pct"]),
                    str(r["mrr_at_5"]),
                ]
            )
        )
    md = (
        f"""# OS29 Benchmark Results

> **Fixed synthetic dataset** — `seed={SEED}`, `N={N}` synthetic episodes, `100` queries.
> Re-run locally: `python benchmarks/run_benchmark.py`

## Retrieval Performance

|{"| ".join(hdr)}|
|{sep}|
"""
        + "\n".join(f"|{r}|" for r in rows[2:])
        + """

## Reproduce

```bash
git clone --branch release/os28-os29-clean https://github.com/gyodragos-cell/ana-max-os29.git
cd ana-max-os29
python benchmarks/run_benchmark.py
cat benchmarks/results.json
```

*Measured on the host running the script. Timings vary; these are not a universal performance claim.*
"""
    )
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "BENCHMARKS.md").write_text(md, encoding="utf-8", newline="\n")
    print("\nSaved: benchmarks/results.json | docs/BENCHMARKS.md")
    return results


if __name__ == "__main__":
    main()
