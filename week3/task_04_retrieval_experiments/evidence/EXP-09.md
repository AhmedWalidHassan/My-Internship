### EXP-09  {'HYBRID_BM25_WEIGHT': '0.3', 'SOURCE_PRIOR': 'meetings/:0.5,newsletters/:0.5', 'CHUNK_SIZE': '400', 'CHUNK_OVERLAP': '50'}
retriever: hybrid (BM25 0.3 + dense 0.7), source prior meetings/:0.5,newsletters/:0.5, depth 10 per retriever | index: {'chunks': 588, 'rebuilt': False, 'seconds': 0.05, 'embedded_chunks': 0} | wall 5.7 s
| | Baseline | This | Delta |
|---|---:|---:|---:|
| recall@1 | 0.417 | 0.683 | +0.267 |
| recall@3 | 0.800 | 0.917 | +0.117 |
| recall@5 | 0.917 | 0.933 | +0.017 |
| recall@10 | 0.933 | 0.933 | +0.000 |
| mrr | 0.612 | 0.793 | +0.181 |
| latency p50 / p95 per query | 0.6 / 0.9 ms | 0.7 / 1.2 ms | |

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.000 | 1.000 | 0.642 | 0.733 |
| table | 4 | 1.000 | 1.000 | 0.833 | 1.000 |
| keyword | 4 | 1.000 | 1.000 | 0.708 | 0.833 |
| version | 5 | 1.000 | 1.000 | 0.800 | 0.900 |
| conflict | 3 | 1.000 | 1.000 | 0.556 | 0.778 |
| draft | 4 | 1.000 | 1.000 | 0.446 | 0.812 |
| multi_hop | 4 | 1.000 | 1.000 | 0.646 | 0.708 |
| multi_part | 4 | 0.750 | 1.000 | 0.542 | 0.875 |
| ambiguous | 3 | 1.000 | 1.000 | 0.667 | 0.833 |
| long_doc | 4 | 1.000 | 1.000 | 0.833 | 1.000 |
| cross_lingual | 4 | 0.250 | 0.250 | 0.062 | 0.125 |
| follow_up | 4 | 1.000 | 1.000 | 0.521 | 0.875 |
| personalized | 4 | 0.750 | 0.750 | 0.312 | 0.750 |
| access | 3 | 1.000 | 1.000 | 1.000 | 1.000 |

examples whose recall@5 changed: [('17', 0.0, 1.0)]
