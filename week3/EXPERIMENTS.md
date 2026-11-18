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

**Result** *(committed after running)*: *(pending)*

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
