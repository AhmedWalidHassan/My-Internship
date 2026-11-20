### EXP-07  {'SOURCE_PRIOR': 'meetings/:0.5,newsletters/:0.5'}
retriever: hybrid (BM25 + dense), source prior meetings/:0.5,newsletters/:0.5, depth 10 per retriever | index: {'chunks': 348, 'rebuilt': False, 'seconds': 0.05, 'embedded_chunks': 0} | wall 6.2 s
| | Baseline | This | Delta |
|---|---:|---:|---:|
| recall@1 | 0.417 | 0.450 | +0.033 |
| recall@3 | 0.800 | 0.850 | +0.050 |
| recall@5 | 0.917 | 0.933 | +0.017 |
| recall@10 | 0.933 | 0.933 | +0.000 |
| mrr | 0.612 | 0.643 | +0.031 |
| latency p50 / p95 per query | 0.6 / 0.9 ms | 0.6 / 0.9 ms | |

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.000 | 1.000 | 0.642 | 0.667 |
| table | 4 | 1.000 | 1.000 | 0.833 | 0.833 |
| keyword | 4 | 1.000 | 1.000 | 0.708 | 0.708 |
| version | 5 | 1.000 | 1.000 | 0.800 | 0.800 |
| conflict | 3 | 1.000 | 1.000 | 0.556 | 0.556 |
| draft | 4 | 1.000 | 1.000 | 0.446 | 0.458 |
| multi_hop | 4 | 1.000 | 1.000 | 0.646 | 0.646 |
| multi_part | 4 | 0.750 | 1.000 | 0.542 | 0.583 |
| ambiguous | 3 | 1.000 | 1.000 | 0.667 | 0.667 |
| long_doc | 4 | 1.000 | 1.000 | 0.833 | 0.875 |
| cross_lingual | 4 | 0.250 | 0.250 | 0.062 | 0.062 |
| follow_up | 4 | 1.000 | 1.000 | 0.521 | 0.562 |
| personalized | 4 | 0.750 | 0.750 | 0.312 | 0.583 |
| access | 3 | 1.000 | 1.000 | 1.000 | 1.000 |

examples whose recall@5 changed: [('17', 0.0, 1.0)]
