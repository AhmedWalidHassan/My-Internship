# Week 3 — Experiment Log

> **Standing rule 4:** write the hypothesis and commit it **before** you run the
> experiment. Then run it, fill in the result, and commit again. Your reviewer will
> check the order in `git log -p EXPERIMENTS.md`.
>
> **Standing rule 5:** tune on dev. Run test only to confirm the final choice.

---

## Noise floor

Three runs of the unchanged baseline on dev: the Task 3 ingestion, the hybrid retriever (BM25 0.5 /
dense 0.5, weighted RRF), all-MiniLM-L6-v2, depth 10, 60 answerable dev questions.
`week3/task_04_retrieval_experiments/scripts/run_experiment.py baseline-N` (2026-11-18).

| Run | recall@5 | MRR | Notes |
|---:|---:|---:|---|
| 1 | 0.917 | 0.612 | laptop GPU, PyTorch (the baseline everything below is compared with) |
| 2 | 0.917 | 0.612 | same: identical document rankings for all 60 questions |
| 3 | 0.917 | 0.612 | same |
| **Spread (max − min)** | **0.000** | **0.000** | |
| *extra:* fastembed / ONNX, index rebuilt (what CI runs) | 0.917 | 0.612 | identical rankings for 60/60 |
| *extra:* CPU PyTorch, index rebuilt (what the container runs) | 0.917 | 0.612 | identical rankings for 60/60 |

**Is retrieval deterministic? Why or why not?**

> **Yes, fully, on every backend this project runs.** No LLM is involved (no multi-query, no HyDE). The
> FAISS index is a flat, exact search, not approximate. BM25 is pure counting. The embedding model is a
> fixed function, and its float differences between GPU PyTorch, CPU PyTorch and ONNX Runtime are too
> small to flip any rank in the top 10 (checked on rebuilt indexes, embedding cache off). Two kinds of
> change *could* move it: a library upgrade that changes tie-breaking or tokenisation, or anything
> stochastic in the retriever. None is in the baseline.

**Smallest difference I'll treat as real:** recall@5 ± **0.017** (one of 60 questions) · MRR ± **0.008**
(one question moving from rank 1 to rank 2: 0.5/60). With zero noise, every change of at least one
question is real, so the resolution of the metric *is* the threshold. With n = 60, though, one question
is 1.7 points, so a difference of one or two questions says little about the holdout.

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

Every experiment is the baseline (the noise-floor config) plus ONE change, run with
`run_experiment.py`, retrieval-only, dev. Per-example results: `week3/task_04_retrieval_experiments/evidence/<ID>_dev.json`.
The hypotheses for EXP-01 to EXP-07 were committed together, before any of them was run.

### EXP-01 — More dense, less BM25 (hybrid weight 0.5 → 0.3)

**Hypothesis** *(committed before running)*: If I lower the BM25 share of the fusion from 0.5 to 0.3, then **multi_part improves** (#17 "What are the password rules?" comes back into the top 5: it is lost today because three meeting notes about a "password reset flow" win on BM25), while **keyword MRR drops** (E-301, NW-BAT-4380, Fleet Manager 4.3 are exact tokens that BM25 ranks first and dense blurs) but keyword recall@5 holds. Overall recall@5 +0.017 (one question), MRR within ±0.03.

**The one change:** more dense, less bm25 (hybrid weight 0.5 → 0.3).

**Config diff:**
```
HYBRID_BM25_WEIGHT: 0.5 -> 0.3
```

**Result** *(committed after running)*: `hybrid (BM25 0.3 + dense 0.7), depth 10 per retriever`, 348 chunks.

| | Baseline | This | Delta | Bigger than noise? |
|---|---:|---:|---:|---|
| recall@5 (all) | 0.917 | 0.917 | +0.000 | no (identical) |
| MRR (all) | 0.612 | 0.685 | +0.073 | yes |
| recall@1 (all) | 0.417 | 0.533 | +0.117 | yes |
| Latency / query (p50 / p95) | 0.6 / 0.9 ms | 0.6 / 0.9 ms | | – |
| Cost / query | $0 local (≈ 12 query tokens = $0.0000002 hosted) | same | 0 | – |

Categories that moved (any recall@5 change, or MRR by more than 0.008):

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.00 | 1.00 | 0.64 | 0.78 |
| table | 4 | 1.00 | 1.00 | 0.83 | 0.80 |
| keyword | 4 | 1.00 | 1.00 | 0.71 | 0.88 |
| version | 5 | 1.00 | 1.00 | 0.80 | 0.85 |
| draft | 4 | 1.00 | 0.75 | 0.45 | 0.30 |
| multi_part | 4 | 0.75 | 1.00 | 0.54 | 0.68 |
| ambiguous | 3 | 1.00 | 1.00 | 0.67 | 0.83 |
| long_doc | 4 | 1.00 | 1.00 | 0.83 | 0.88 |
| cross_lingual | 4 | 0.25 | 0.25 | 0.06 | 0.08 |
| follow_up | 4 | 1.00 | 1.00 | 0.52 | 0.75 |
| personalized | 4 | 0.75 | 0.75 | 0.31 | 0.46 |

Questions in/out of the top 5: n08 lost, 17 gained.

**Hypothesis confirmed?** **Partly.**
- **Right:** #17 came back (multi_part 0.75 → 1.00) and recall@5 held overall.
- **Wrong about keyword:** its MRR *rose* (0.71 → 0.88). The exact-code questions are just as well
  served by dense once the context line ("Rover Error Codes 2026 › Error codes") is in the vector.
- **Missed entirely:** MRR rose across the board (+0.073; recall@1 +0.117). Lowering BM25's weight
  mostly removes the noise of word-overlap matches from chatty documents.
- **The cost I didn't predict:** `draft` lost n08 ("Is Northwind switching to flexible time off?",
  R@5 1.00 → 0.75). Dense ranks newsletters and the PTO policy above the FTO draft, whose words BM25
  matched exactly.

**Decision:** follow up. The direction is right, and EXP-08 combines it with the levers that don't
cost a question.

---

### EXP-02 — Dense only (no BM25)

**Hypothesis** *(committed before running)*: If I drop BM25 entirely, then retrieval gets **worse**: **keyword** loses at least one question at recall@5 (error and part codes are exact strings a 384-dimension MiniLM vector can't distinguish: 4380 vs 4830), **table** and **version** MRR fall (IDs like FIN-POL-002 in the context line match by BM25 today), and overall MRR drops by ≥ 0.05. #17 comes back (BM25 caused it). cross_lingual doesn't change (the dense model is English-only anyway).

**The one change:** dense only (no bm25).

**Config diff:**
```
HYBRID_BM25_WEIGHT: 0.5 -> 0.0
```

**Result** *(committed after running)*: `dense only, depth 10 per retriever`, 348 chunks.

| | Baseline | This | Delta | Bigger than noise? |
|---|---:|---:|---:|---|
| recall@5 (all) | 0.917 | 0.900 | -0.017 | yes |
| MRR (all) | 0.612 | 0.752 | +0.140 | yes |
| recall@1 (all) | 0.417 | 0.633 | +0.217 | yes |
| Latency / query (p50 / p95) | 0.6 / 0.9 ms | 0.2 / 0.3 ms | | – |
| Cost / query | $0 local (≈ 12 query tokens = $0.0000002 hosted) | same | 0 | – |

Categories that moved (any recall@5 change, or MRR by more than 0.008):

| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |
|---|---:|---:|---:|---:|---:|
| factual | 10 | 1.00 | 1.00 | 0.64 | 0.78 |
| table | 4 | 1.00 | 0.75 | 0.83 | 0.75 |
| keyword | 4 | 1.00 | 1.00 | 0.71 | 0.75 |
| version | 5 | 1.00 | 1.00 | 0.80 | 0.90 |
| draft | 4 | 1.00 | 0.75 | 0.45 | 0.59 |
| multi_hop | 4 | 1.00 | 1.00 | 0.65 | 0.71 |
| multi_part | 4 | 0.75 | 1.00 | 0.54 | 0.88 |
| ambiguous | 3 | 1.00 | 1.00 | 0.67 | 0.83 |
| long_doc | 4 | 1.00 | 1.00 | 0.83 | 0.88 |
| cross_lingual | 4 | 0.25 | 0.25 | 0.06 | 0.25 |
| follow_up | 4 | 1.00 | 1.00 | 0.52 | 0.88 |
| personalized | 4 | 0.75 | 0.75 | 0.31 | 0.75 |

Questions in/out of the top 5: n02 lost, n08 lost, 17 gained.

**Hypothesis confirmed?** **Partly. Recall@5 got worse, as predicted, but by one question, not "at
least one keyword", and MRR went *up* a lot, the opposite of what I predicted.**
- **The losses:** n02 (the 5G module's price: `table` 1.00 → 0.75, the parts-catalog row only BM25
  finds) and n08 (the FTO draft question).
- **The gains:** dense alone ranks the right document first far more often (MRR 0.612 → 0.752,
  recall@1 0.417 → 0.633). BM25's equal vote was pulling chatty, word-sharing chunks up.
- **What I learned:** in this corpus BM25 is a *recall* safety net for exact strings and rare words,
  not a ranking signal. It should keep a small weight, not zero: EXP-01's 0.3 kept n02. This is also
  the one experiment whose average hides a trade-off. MRR says "big win", recall@5 says "lost a
  question", and the question lost is a price lookup a user would care about.

**Decision:** revert (don't drop BM25). Keep its weight as a lever for EXP-08.

---

### EXP-03 — No contextual chunk header

**Hypothesis** *(committed before running)*: If I stop prepending `<title> [<id> v<version> · <status> · effective <date>] › <section>` to every chunk (Task 3), then retrieval gets **worse**, mostly in MRR (≥ 0.05 overall): **version / draft / conflict** (the header carries the document ID, version and status that distinguish PTO v2, v3 and the draft), **table** and **keyword** (a table row like "Tier: B | …" no longer says it is the Travel & Per Diem Policy), **long_doc** (a manual chunk no longer says "R3 Operator Manual › 14. Floors, ramps"). Recall@5 drops by at least one question.

**The one change:** no contextual chunk header.

**Config diff:**
```
CHUNK_CONTEXT_HEADER: true -> false   (own index)
```

**Result** *(committed after running)*: *(pending)*

---

### EXP-04 — Smaller chunks (800/100 → 400/50)

**Hypothesis** *(committed before running)*: If I halve the chunk size, then **long_doc and factual MRR improve slightly** (a needle sentence dominates a smaller chunk's vector) but **multi_part and multi_hop get worse** (the answer's parts, e.g. referral amount + timing, password length + MFA + rotation, are split across chunks, so the top 5 holds fewer of them), and BM25's per-chunk statistics shift. Net overall recall@5 within ±0.02 and MRR within ±0.03, i.e. no clear win, at roughly 1.6× the chunks.

**The one change:** smaller chunks (800/100 → 400/50).

**Config diff:**
```
CHUNK_SIZE: 800 -> 400, CHUNK_OVERLAP: 100 -> 50   (own index)
```

**Result** *(committed after running)*: *(pending)*

---

### EXP-05 — Multilingual embedding model

**Hypothesis** *(committed before running)*: If I replace all-MiniLM-L6-v2 with paraphrase-multilingual-MiniLM-L12-v2 (same 384 dimensions, trained to map translations to the same vector), then **cross_lingual rises from 0.25 to ≥ 0.75** at recall@5 (the Arabic Cairo pages finally land near English questions). English categories lose a little MRR (−0.02 to −0.05: a 12-layer multilingual model spreads its capacity over 50 languages), and recall@5 holds because BM25 still anchors exact terms. The index costs about 2× to build (12 layers vs 6).

**The one change:** multilingual embedding model.

**Config diff:**
```
HF_EMBED_MODEL: sentence-transformers/all-MiniLM-L6-v2 -> sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2   (own index)
```

**Result** *(committed after running)*: *(pending)*

---

### EXP-06 — Cross-encoder re-ranker over the top 20

**Hypothesis** *(committed before running)*: If I re-rank the hybrid's top 20 candidates per retriever with cross-encoder/ms-marco-MiniLM-L-6-v2, then **MRR rises by ≥ 0.05** and recall@1 by ≥ 0.10 (a cross-encoder reads question and passage together, so it should put the policy above the meeting note that merely shares words: #17 returns). But **cross_lingual drops to 0** (an English-only cross-encoder scores Arabic passages as irrelevant and pushes the one CSV row we find today out of the top 5). Latency: +20–60 ms per query on the GPU, **+150–400 ms on CPU** (the container), against ~1 ms for retrieval today.

**The one change:** cross-encoder re-ranker over the top 20.

**Config diff:**
```
RERANKER_MODEL: (none) -> cross-encoder/ms-marco-MiniLM-L-6-v2, RERANK_TOP_N: 20
```

**Result** *(committed after running)*: *(pending)*

---

### EXP-07 — Source prior: down-weight meeting notes and newsletters

**Hypothesis** *(committed before running)*: If I multiply the fused score of chunks from `meetings/` and `newsletters/` by 0.5, then **#17 returns** (multi_part 0.75 → 1.00) and **MRR rises slightly** (+0.01 to +0.03) on policy questions where chatter competes ("carry over" in 35 meeting notes, "PTO" in 53). **No dev question loses**, because no dev gold document is a meeting note or a newsletter, which is also this experiment's risk: it bakes in a judgment (chatter is less authoritative) that the holdout could punish if it asks about something only a meeting note says.

**The one change:** source prior: down-weight meeting notes and newsletters.

**Config diff:**
```
SOURCE_PRIOR: (none) -> meetings/:0.5,newsletters/:0.5
```

**Result** *(committed after running)*: *(pending)*

---

## Summary

| ID | Change | R@5 Δ | MRR Δ | Latency Δ | Decision |
|---|---|---:|---:|---:|---|
| EXP-01 | BM25 weight 0.5 → 0.3 | | | | |
| EXP-02 | dense only | | | | |
| EXP-03 | no context header | | | | |
| EXP-04 | chunks 800 → 400 | | | | |
| EXP-05 | multilingual embeddings | | | | |
| EXP-06 | cross-encoder re-ranker | | | | |
| EXP-07 | source prior | | | | |
