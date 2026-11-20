# Cache hit rate on a repeated-question workload (120 requests, --users one)

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
- **Who asks** (Week 3 Task 6, `--users`): `one` = every request from the same employee (u1001):
  one access scope, what the Week 2 cache saw. `directory` = each new session from one of the six
  directory users, uniformly (4 access scopes: 3 employees share one). The question plan is the
  same for both (drawn first, from the same seed); a follow-up stays with its session's user.

**Hit rate: 84/120 = 70%**

| Outcome | Requests | % |
|---|---:|---:|
| hit | 84 | 70% |
| miss: first time this question was asked | 23 | 19% |
| miss: follow-up (never cached, by design) | 9 | 8% |
| miss: paraphrase (only a semantic cache could hit) | 4 | 3% |

| Asked as | Requests | Hit rate |
|---|---:|---:|
| exact | 85 | 79% |
| variant | 18 | 72% |
| paraphrase | 8 | 50% |
| follow-up | 9 | 0% |

| | With the cache (measured) | Without (estimated: every request at the mean miss cost/latency) |
|---|---:|---:|
| Total LLM cost | $0.0308 | $0.1028 |
| Total answer time | 242 s | 808 s |
| Mean / p95 latency | 2.02 s / 10.06 s | 6.74 s / 15.08 s (misses only) |

Wall clock 243 s. Embedding cache over the run: 1 hits, 58 misses (query embeddings; the corpus index was loaded, not re-embedded).
