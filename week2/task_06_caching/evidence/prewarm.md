# Pre-warming the cache at startup (stretch): a cold-start user asks the top 10 questions

| | User mean latency | User p95 latency | Cache hits | Startup work |
|---|---:|---:|---:|---:|
| no pre-warm | 3.41 s | 6.83 s | 0/10 | 0.0 s of LLM work |
| pre-warmed (10 questions) | <1 ms | <1 ms | 10/10 | 32.2 s of LLM work |
