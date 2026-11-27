# OS29 Benchmark Results

> **Fixed synthetic dataset** — `seed=42`, `N=500` synthetic episodes, `100` queries.
> Re-run locally: `python benchmarks/run_benchmark.py`

## Retrieval Performance

|Method| p50 (ms)| p95 (ms)| p99 (ms)| Recall@5 (%)| MRR@5|
|---|---|---|---|---|---|
|Baseline-1 (Python dict+LIKE)|0.0888|0.0933|0.1158|70.0|0.3197|
|Baseline-2 (regex full-scan)|0.37|0.5337|0.5954|70.0|0.3197|
|OS29 FTS5/BM25 (WAL)|0.0625|0.1137|0.1773|70.0|0.3197|

## Reproduce

```bash
git clone --branch release/os28-os29-clean https://github.com/gyodragos-cell/ana-max-os29.git
cd ana-max-os29
python benchmarks/run_benchmark.py
cat benchmarks/results.json
```

*Measured on the host running the script. Timings vary; these are not a universal performance claim.*
