### EXP-05  {'HF_EMBED_MODEL': 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'}
retriever: hybrid (BM25 + dense), depth 10 per retriever | index: {'chunks': 348, 'rebuilt': True, 'seconds': 6.32, 'embedded_chunks': 348} | wall 45.8 s
| | Baseline | This | Delta |
|---|---:|---:|---:|
| recall@1 | 0.417 | 0.383 | -0.033 |
| recall@3 | 0.800 | 0.633 | -0.167 |
| recall@5 | 0.917 | 0.833 | -0.083 |
| recall@10 | 0.933 | 0.917 | -0.017 |
| mrr | 0.612 | 0.556 | -0.055 |
| latency p50 / p95 per query | 0.6 / 0.9 ms | 5.9 / 9.5 ms | |

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.000 | 0.600 | 0.642 | 0.359 |
| table | 4 | 1.000 | 1.000 | 0.833 | 1.000 |
| keyword | 4 | 1.000 | 1.000 | 0.708 | 0.675 |
| version | 5 | 1.000 | 0.800 | 0.800 | 0.733 |
| conflict | 3 | 1.000 | 1.000 | 0.556 | 0.583 |
| draft | 4 | 1.000 | 1.000 | 0.446 | 0.396 |
| multi_hop | 4 | 1.000 | 1.000 | 0.646 | 0.625 |
| multi_part | 4 | 0.750 | 1.000 | 0.542 | 0.688 |
| ambiguous | 3 | 1.000 | 1.000 | 0.667 | 0.344 |
| long_doc | 4 | 1.000 | 0.750 | 0.833 | 0.604 |
| cross_lingual | 4 | 0.250 | 0.750 | 0.062 | 0.244 |
| follow_up | 4 | 1.000 | 0.750 | 0.521 | 0.438 |
| personalized | 4 | 0.750 | 0.500 | 0.312 | 0.417 |
| access | 3 | 1.000 | 1.000 | 1.000 | 1.000 |

examples whose recall@5 changed: [('19', 1.0, 0.0), ('24', 1.0, 0.0), ('4', 1.0, 0.0), ('6', 1.0, 0.0), ('3', 1.0, 0.0), ('17', 0.0, 1.0), ('n12', 1.0, 0.0), ('n16', 0.0, 1.0), ('s25', 0.0, 1.0), ('36', 1.0, 0.0), ('n25', 1.0, 0.0)]
