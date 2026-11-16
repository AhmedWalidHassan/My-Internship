# Cache hit rate on a repeated-question workload (120 requests)

**Workload (defined, deterministic: `--seed 7`):** N requests from employees, one at a time.
- **Which question:** the 28 eval questions (24 answerable + 4 out-of-scope) with Zipf-like
  popularity (weight 1/rank^1.1, rank = eval-set order), so a few questions dominate, like a
  real internal FAQ.
- **How it is asked** (first question of a new session):
  - 60%: the exact eval wording;
  - 25%: a trivial variant (lowercase, no question mark, extra spaces), which normalisation
    should absorb;
  - 15%: a real paraphrase, for the 10 questions that have one (else exact). Only a semantic
    cache could hit on those.
- **Follow-ups:** 10% of requests are instead a SECOND turn in an earlier session ("Are there
  any exceptions?", ...). They are never cacheable, by design.

**Hit rate: 87/120 = 72%**

| Outcome | Requests | % |
|---|---:|---:|
| hit | 87 | 72% |
| miss: first time this question was asked | 18 | 15% |
| miss: follow-up (never cached, by design) | 11 | 9% |
| miss: paraphrase (only a semantic cache could hit) | 4 | 3% |

| Asked as | Requests | Hit rate |
|---|---:|---:|
| exact | 76 | 82% |
| variant | 25 | 84% |
| paraphrase | 8 | 50% |
| follow-up | 11 | 0% |

| | With the cache (measured) | Without (estimated: every request at the mean miss cost/latency) |
|---|---:|---:|
| Total LLM cost | $0.0181 | $0.0657 |
| Total answer time | 145 s | 526 s |
| Mean / p95 latency | 1.21 s / 5.90 s | 4.38 s / 9.44 s (misses only) |

Wall clock 145 s. Embedding cache over the run: 5 hits, 52 misses (query embeddings; the corpus index was loaded, not re-embedded).
