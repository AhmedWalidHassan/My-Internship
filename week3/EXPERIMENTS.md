# Week 3 — Experiment Log

> **Standing rule 4:** write the hypothesis and commit it **before** you run the
> experiment. Then run it, fill in the result, and commit again. Your reviewer will
> check the order in `git log -p EXPERIMENTS.md`.
>
> **Standing rule 5:** tune on dev. Run test only to confirm the final choice.

---

## Noise floor

Three runs of the unchanged baseline on dev.

| Run | recall@5 | MRR | Notes |
|---|---:|---:|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| **Spread (max − min)** | | | |

**Is retrieval deterministic? Why or why not?**

>

**Smallest difference I'll treat as real:** recall@5 ± ___ · MRR ± ___

---

## Task 3 — ING-01: ingestion that reads every format

**Hypothesis** *(committed before running, 2026-11-18)*: If I replace the Week 2 loader (`.md`/`.txt`
only, 118 of 190 documents) with per-format loaders, then dev **recall@5 overall rises from 0.13 to at
least 0.60** (MRR from 0.08 to at least 0.45). The loaders: PDF with page furniture removed and tables
rebuilt as rows; HTML with the wiki chrome dropped; XLSX rows carrying their column headers; CSV rows
the same way; Unicode NFKC everywhere. Every chunk also gets `_metadata.csv` plus parsed metadata. The
reason: Task 2 measured that 47 of the 52 retrieval misses on dev are questions whose gold document the
loader can't read at all. Making them readable lifts the ceiling from 13/60 to 60/60, and BM25 + dense
on clean text should find most of them.

Per category, what I expect to move (dev recall@5):

| Category | Before (Task 2) | Expected after | Why |
|---|---:|---|---|
| version, table, multi_part, follow_up, personalized | 0.00 | ≥ 0.6 | gold docs are policy / SLA PDFs, unreadable before |
| factual, conflict, keyword, multi_hop | 0.00–0.25 | ≥ 0.5 | mostly PDF/HTML/XLSX gold docs; keyword needs exact IDs, so NFKC and rejoined IDs (`IT-STD-009`) matter |
| long_doc | 0.00 | 0.25–0.5 only | the manual becomes readable, but 81% of its sentences are repeated boilerplate that crowds the top 5 |
| access (authorised) | 0.33 | ≥ 0.6 | the PDF/XLSX restricted docs become readable (which also makes the leak risk worse until Task 6) |
| draft | 1.00 | may **drop** to ≥ 0.75 | the FTO draft now competes with PTO v2, v3 and the wiki for the same words |
| cross_lingual | 0.00 | **stays ~0** | the Arabic pages were already readable. The English-only embedding model is the problem, not ingestion (a Task 4 experiment) |

Chunk count: 139 → roughly 350–450 (Task 1 measured 378 chunks for a naive extraction of all 190).
Dedup should find the wiki pages that mirror a policy (Password Policy ↔ IT-STD-003) and the legacy
intranet copies. I expect it to change recall by less than the noise. Its job is fewer duplicate chunks
in the top k and less grading cost, not recall.

**Result** *(committed after running, 2026-11-18)*:

| | Before (Task 2) | After | Delta | Bigger than noise? |
|---|---:|---:|---:|---|
| Documents loaded | 118 / 190 | **190 / 190** | +72 | – |
| Chunks | 139 | 348 | +209 | – |
| recall@5 (all, dev) | 0.133 | **0.917** | **+0.783** | yes: retrieval is deterministic (two runs gave identical rankings for all 60 examples) |
| MRR (all, dev) | 0.076 | **0.612** | +0.536 | yes |
| Retrieval latency / query | 3.1 ms p50 | 0.9–1.0 ms p50 | ≈ | – |
| Cost / question (full pipeline, gpt-4o-mini prices) | $0.000687 | $0.000698 | +1.7% | – |

| Category | Before R@5 | After R@5 | My prediction |
|---|---:|---:|---|
| factual | 0.10 | 1.00 | ≥ 0.5 ✓ |
| table | 0.00 | 1.00 | ≥ 0.6 ✓ |
| keyword | 0.25 | 1.00 | ≥ 0.5 ✓ |
| version | 0.00 | 1.00 | ≥ 0.6 ✓ |
| conflict | 0.00 | 1.00 | ≥ 0.5 ✓ |
| draft | 1.00 | 1.00 | "may drop to ≥ 0.75": **didn't drop** (but R@1 is 0.25: the draft competes for first place) |
| multi_hop | 0.00 | 1.00 | ≥ 0.5 ✓ |
| multi_part | 0.00 | 0.75 | ≥ 0.6 ✓ |
| ambiguous | 0.33 | 1.00 | (no prediction) |
| long_doc | 0.00 | **1.00** | "0.25–0.5 only": **wrong, it did much better** |
| cross_lingual | 0.00 | 0.25 | "stays ~0" ✓ (one CSV row found) |
| follow_up | 0.00 | 1.00 | ≥ 0.6 ✓ |
| personalized | 0.00 | 0.75 | ≥ 0.6 ✓ |
| access (authorised) | 0.33 | 1.00 | ≥ 0.6 ✓ |

**Hypothesis confirmed?** **Yes, and the overall effect is larger than predicted.** recall@5 0.92
against a predicted ≥ 0.60, MRR 0.61 against ≥ 0.45. Lessons:

- **I was wrong about `long_doc`.** I expected the manual's boilerplate to crowd the top 5 even after
  parsing. But dropping the repeated sentences at parse time (1,064 of 1,099) shrank 23 pages to 6
  chunks, so the needles now sit in short, distinctive chunks. The boilerplate fix belonged in
  ingestion, not in retrieval.
- **`draft` didn't drop at recall@5, but recall@1 is 0.25:** the draft now competes with PTO v2/v3 for
  first place. That's the ranking problem Task 5 has to solve with `status`.
- **The 5 misses left:**
  - 4 are the Arabic pages (the English-only embedding model, a Task 4 experiment).
  - 1 is "What are the password rules?", where meeting notes about a "password reset flow" outrank
    IT-STD-003: the lexical trap from Task 1 issue #10.
- **Dedup changed recall by exactly 0, as predicted:** it labels a copy (`duplicate_of`), it doesn't
  remove it from retrieval.

**Decision:** keep. This is the new baseline for Task 4 (`eval_baseline.json` re-set on it).

---

## Experiments

Copy this block once per experiment. Commit the top half first.

### EXP-01 — <short name>

**Hypothesis** *(committed before running)*: If I change ___, then ___ will
improve/worsen in categories ___, because ___.

**The one change:** 

**Config diff:**
```
```

**Result** *(committed after running)*:

| | Baseline | This | Delta | Bigger than noise? |
|---|---:|---:|---:|---|
| recall@5 (all) | | | | |
| MRR (all) | | | | |
| Latency / query | | | | |
| Cost / query | | | | |

Categories that moved by more than the noise floor:

| Category | Baseline R@5 | This R@5 |
|---|---:|---:|
| | | |

**Hypothesis confirmed?** Yes / No / Partly — and what I learned:

>

**Decision:** keep / revert / follow up with EXP-__

---

## Summary

| ID | Change | R@5 Δ | MRR Δ | Latency Δ | Decision |
|---|---|---:|---:|---:|---|
| EXP-01 | | | | | |
| EXP-02 | | | | | |
| EXP-03 | | | | | |
| EXP-04 | | | | | |
| EXP-05 | | | | | |
