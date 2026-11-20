### EXP-02  {'HYBRID_BM25_WEIGHT': '0.0'}
retriever: dense only, depth 10 per retriever | index: {'chunks': 348, 'rebuilt': False, 'seconds': 0.05, 'embedded_chunks': 0} | wall 6.0 s
| | Baseline | This | Delta |
|---|---:|---:|---:|
| recall@1 | 0.417 | 0.633 | +0.217 |
| recall@3 | 0.800 | 0.867 | +0.067 |
| recall@5 | 0.917 | 0.900 | -0.017 |
| recall@10 | 0.933 | 0.917 | -0.017 |
| mrr | 0.612 | 0.752 | +0.140 |
| latency p50 / p95 per query | 0.6 / 0.9 ms | 0.2 / 0.3 ms | |

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.000 | 1.000 | 0.642 | 0.775 |
| table | 4 | 1.000 | 0.750 | 0.833 | 0.750 |
| keyword | 4 | 1.000 | 1.000 | 0.708 | 0.750 |
| version | 5 | 1.000 | 1.000 | 0.800 | 0.900 |
| conflict | 3 | 1.000 | 1.000 | 0.556 | 0.556 |
| draft | 4 | 1.000 | 0.750 | 0.446 | 0.594 |
| multi_hop | 4 | 1.000 | 1.000 | 0.646 | 0.708 |
| multi_part | 4 | 0.750 | 1.000 | 0.542 | 0.875 |
| ambiguous | 3 | 1.000 | 1.000 | 0.667 | 0.833 |
| long_doc | 4 | 1.000 | 1.000 | 0.833 | 0.875 |
| cross_lingual | 4 | 0.250 | 0.250 | 0.062 | 0.250 |
| follow_up | 4 | 1.000 | 1.000 | 0.521 | 0.875 |
| personalized | 4 | 0.750 | 0.750 | 0.312 | 0.750 |
| access | 3 | 1.000 | 1.000 | 1.000 | 1.000 |

examples whose recall@5 changed: [('n02', 1.0, 0.0), ('n08', 1.0, 0.0), ('17', 0.0, 1.0)]
