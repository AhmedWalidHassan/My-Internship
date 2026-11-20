# Cache hit rate on a repeated-question workload (120 requests, --users directory)

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

**Hit rate: 63/120 = 52%**

| Outcome | Requests | % |
|---|---:|---:|
| hit | 63 | 52% |
| miss: first time this question was asked | 23 | 19% |
| miss: first time in this access scope (Task 6) | 20 | 17% |
| miss: follow-up (never cached, by design) | 9 | 8% |
| miss: paraphrase (only a semantic cache could hit) | 5 | 4% |

| Asked as | Requests | Hit rate |
|---|---:|---:|
| exact | 85 | 62% |
| variant | 18 | 39% |
| paraphrase | 8 | 38% |
| follow-up | 9 | 0% |

| | With the cache (measured) | Without (estimated: every request at the mean miss cost/latency) |
|---|---:|---:|
| Total LLM cost | $0.0446 | $0.0940 |
| Total answer time | 335 s | 706 s |
| Mean / p95 latency | 2.79 s / 10.69 s | 5.88 s / 11.94 s (misses only) |

Wall clock 335 s. Embedding cache over the run: 19 hits, 65 misses (query embeddings; the corpus index was loaded, not re-embedded).
