# Cache: cold vs warm, same 20 questions

Model `ollama:qwen3.5:4b` (local), pricing gpt-4o-mini list. Each question in a fresh session. Answer cache entries before the cold pass: 1 (only the warm-up); fresh embedding cache.

| | Mean latency | p95 latency | Mean cost / question | Total run cost | Cache hits | LLM calls | Query embeddings computed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cold cache | 3.64 s | 7.89 s | $0.000444 | $0.008886 | 0/20 | 255 | 28 |
| Warm cache | <1 ms | <1 ms | $0.000000 | $0.000000 | 20/20 | 0 | 0 |
| **Delta** | **−3.64 s (100% less)** | **−7.89 s** | **−$0.000444** | **−$0.008886** | | -255 | |

Cold-pass misses that stayed misses in the warm pass (not cached: refusals beyond the refusal TTL, or failed): 0.
