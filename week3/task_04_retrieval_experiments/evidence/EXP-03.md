### EXP-03  {'CHUNK_CONTEXT_HEADER': 'false'}
retriever: hybrid (BM25 + dense), depth 10 per retriever | index: {'chunks': 344, 'rebuilt': True, 'seconds': 6.35, 'embedded_chunks': 344} | wall 12.9 s
| | Baseline | This | Delta |
|---|---:|---:|---:|
| recall@1 | 0.417 | 0.400 | -0.017 |
| recall@3 | 0.800 | 0.717 | -0.083 |
| recall@5 | 0.917 | 0.883 | -0.033 |
| recall@10 | 0.933 | 0.900 | -0.033 |
| mrr | 0.612 | 0.580 | -0.031 |
| latency p50 / p95 per query | 0.6 / 0.9 ms | 4.5 / 8.1 ms | |

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.000 | 1.000 | 0.642 | 0.628 |
| table | 4 | 1.000 | 1.000 | 0.833 | 0.833 |
| keyword | 4 | 1.000 | 1.000 | 0.708 | 0.521 |
| version | 5 | 1.000 | 1.000 | 0.800 | 0.740 |
| conflict | 3 | 1.000 | 1.000 | 0.556 | 0.750 |
| draft | 4 | 1.000 | 1.000 | 0.446 | 0.433 |
| multi_hop | 4 | 1.000 | 1.000 | 0.646 | 0.646 |
| multi_part | 4 | 0.750 | 1.000 | 0.542 | 0.562 |
| ambiguous | 3 | 1.000 | 1.000 | 0.667 | 0.667 |
| long_doc | 4 | 1.000 | 0.750 | 0.833 | 0.608 |
| cross_lingual | 4 | 0.250 | 0.000 | 0.062 | 0.017 |
| follow_up | 4 | 1.000 | 0.750 | 0.521 | 0.476 |
| personalized | 4 | 0.750 | 0.750 | 0.312 | 0.300 |
| access | 3 | 1.000 | 1.000 | 1.000 | 1.000 |

examples whose recall@5 changed: [('17', 0.0, 1.0), ('n12', 1.0, 0.0), ('n17', 1.0, 0.0), ('36', 1.0, 0.0)]
