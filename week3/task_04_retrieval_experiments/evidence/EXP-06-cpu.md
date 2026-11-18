### EXP-06-cpu  {'RERANKER_MODEL': 'cross-encoder/ms-marco-MiniLM-L-6-v2'}  [CPU]
retriever: hybrid (BM25 + dense), re-ranked by cross-encoder/ms-marco-MiniLM-L-6-v2 (top 20), depth 10 per retriever | index: {'chunks': 348, 'rebuilt': False, 'seconds': 0.05, 'embedded_chunks': 0} | wall 36.7 s
| | Baseline | This | Delta |
|---|---:|---:|---:|
| recall@1 | 0.417 | 0.633 | +0.217 |
| recall@3 | 0.800 | 0.867 | +0.067 |
| recall@5 | 0.917 | 0.917 | +0.000 |
| recall@10 | 0.933 | 0.917 | -0.017 |
| mrr | 0.612 | 0.748 | +0.136 |
| latency p50 / p95 per query | 0.6 / 0.9 ms | 487.5 / 572.4 ms | |

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.000 | 1.000 | 0.642 | 0.833 |
| table | 4 | 1.000 | 1.000 | 0.833 | 0.875 |
| keyword | 4 | 1.000 | 1.000 | 0.708 | 0.875 |
| version | 5 | 1.000 | 1.000 | 0.800 | 0.717 |
| conflict | 3 | 1.000 | 1.000 | 0.556 | 0.583 |
| draft | 4 | 1.000 | 1.000 | 0.446 | 1.000 |
| multi_hop | 4 | 1.000 | 1.000 | 0.646 | 0.875 |
| multi_part | 4 | 0.750 | 1.000 | 0.542 | 0.750 |
| ambiguous | 3 | 1.000 | 1.000 | 0.667 | 0.778 |
| long_doc | 4 | 1.000 | 1.000 | 0.833 | 1.000 |
| cross_lingual | 4 | 0.250 | 0.000 | 0.062 | 0.000 |
| follow_up | 4 | 1.000 | 1.000 | 0.521 | 0.708 |
| personalized | 4 | 0.750 | 0.750 | 0.312 | 0.383 |
| access | 3 | 1.000 | 1.000 | 1.000 | 1.000 |

examples whose recall@5 changed: [('17', 0.0, 1.0), ('n17', 1.0, 0.0)]
