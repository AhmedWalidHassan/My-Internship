### EXP-04  {'CHUNK_SIZE': '400', 'CHUNK_OVERLAP': '50'}
retriever: hybrid (BM25 + dense), depth 10 per retriever | index: {'chunks': 588, 'rebuilt': True, 'seconds': 6.24, 'embedded_chunks': 588} | wall 12.6 s
| | Baseline | This | Delta |
|---|---:|---:|---:|
| recall@1 | 0.417 | 0.417 | +0.000 |
| recall@3 | 0.800 | 0.850 | +0.050 |
| recall@5 | 0.917 | 0.933 | +0.017 |
| recall@10 | 0.933 | 0.933 | +0.000 |
| mrr | 0.612 | 0.639 | +0.027 |
| latency p50 / p95 per query | 0.6 / 0.9 ms | 1.0 / 1.5 ms | |

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.000 | 1.000 | 0.642 | 0.503 |
| table | 4 | 1.000 | 1.000 | 0.833 | 1.000 |
| keyword | 4 | 1.000 | 1.000 | 0.708 | 0.688 |
| version | 5 | 1.000 | 1.000 | 0.800 | 0.800 |
| conflict | 3 | 1.000 | 1.000 | 0.556 | 0.778 |
| draft | 4 | 1.000 | 1.000 | 0.446 | 0.675 |
| multi_hop | 4 | 1.000 | 1.000 | 0.646 | 0.667 |
| multi_part | 4 | 0.750 | 1.000 | 0.542 | 0.562 |
| ambiguous | 3 | 1.000 | 1.000 | 0.667 | 0.500 |
| long_doc | 4 | 1.000 | 1.000 | 0.833 | 1.000 |
| cross_lingual | 4 | 0.250 | 0.250 | 0.062 | 0.062 |
| follow_up | 4 | 1.000 | 1.000 | 0.521 | 0.583 |
| personalized | 4 | 0.750 | 0.750 | 0.312 | 0.375 |
| access | 3 | 1.000 | 1.000 | 1.000 | 1.000 |

examples whose recall@5 changed: [('17', 0.0, 1.0)]
