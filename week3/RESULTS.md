# Week 3 — Results

> **Standing rule 1:** a task is done when its number is in this file, `COST.md`
> or `EXPERIMENTS.md`. Fill these in as you go, not on Friday.
>
> **Standing rule 5:** unless a heading says otherwise, numbers are on **dev**.
> Test numbers appear only where a task asks you to confirm a decision.

Category order used in every table below (15 categories):
`factual · table · keyword · version · conflict · draft · multi_hop · multi_part ·
ambiguous · long_doc · cross_lingual · follow_up · personalized · access · out_of_scope`

---

## Task 1 — Meet the corpus

Measured 2026-11-18 on the laptop (RTX 3060, on AC), local Ollama `qwen3.5:4b` as generator **and**
judge (the Week 2 judges, unchanged), `all-MiniLM-L6-v2` embeddings, hybrid retriever k = 4,
chunks 800/100, `MAX_DOCS_TO_GRADE=6`. Nothing in the product was changed: only `DATA_DIR` (and a
fresh `INDEX_PATH`, so the Week 2 index isn't rewritten). Scripts, raw results and logs:
[`task_01_meet_the_corpus/`](task_01_meet_the_corpus/RUN.md).

Two configurations, because the first one turned out to read almost nothing:

- **W2 as shipped** (`DATA_DIR=week3/corpus`): the official baseline. The Week 2 loader lists
  `DATA_DIR` with `iterdir()` (top level only) and keeps `.md`/`.txt` only, so it indexes **one
  file, the export's own `README.md`, and 0 of the 190 documents**.
- **Recursive view** (diagnostic): the same loader fed every `.md`/`.txt` under the corpus (a
  folder of symlinks, [`corpus_view.py`](task_01_meet_the_corpus/scripts/corpus_view.py); no code
  change). 118 of 190 documents load; every PDF, HTML, XLSX and CSV is still skipped. This shows
  what the Week 2 *pipeline* (chunker, retriever, graders, prompts) does with what it can read.

### The cliff — Week 2 system, new corpus, seed set (40)

Cells are **W2 as shipped / recursive view**. Deterministic = `eval/scoring.py`; correctness and
groundedness = the Week 2 judges. `user_id` is ignored (Week 2 has no users), so every question is
asked anonymously. Per-example tables: [shipped](task_01_meet_the_corpus/evidence/seed_eval_literal.md),
[recursive](task_01_meet_the_corpus/evidence/seed_eval_recursive.md).

| Category | n | Deterministic pass | Correctness | Groundedness |
|---|---:|---:|---:|---:|
| factual | 4 | 0% / 50% | 0.00 / 0.25 | 1.00 / 1.00 |
| table | 3 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| keyword | 3 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| version | 6 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| conflict | 2 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| draft | 1 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| multi_hop | 2 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| multi_part | 2 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| ambiguous | 1 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| long_doc | 2 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| cross_lingual | 3 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| follow_up | 2 | 0% / 0% | 0.00 / 0.00 | 1.00 / 1.00 |
| personalized | 1 | 0% / 0% | 0.00 / 0.00 | 1.00 / 0.00 |
| access | 5 | 60% / 60% | 0.60 / 0.60 | 1.00 / 1.00 |
| out_of_scope | 3 | 100% / 67% | 1.00 / 0.67 | 1.00 / 1.00 |
| **All** | 40 | **15% / 18%** | **0.15 / 0.15** | **1.00 / 0.97** |

How to read it:

- **Every point the shipped system scores is a refusal** (6 of 40: 3 out-of-scope, 3 `access`
  questions from a user who must be refused). It refused 40 of 40. Groundedness 1.00 is the
  refusals scoring as trivially grounded. That metric says nothing on this corpus.
- **`access` 60% is not access control.** The shipped system refuses everyone, so it "protects"
  salaries by knowing nothing. The recursive view shows the real baseline: **s20 leaked Project
  Juniper** (an `hr-leadership` document: "18 roles", "November 12") to u1001, a Robotics Engineer.
  s21 (calibration guide) was answered correctly *for a manager*, and it would be answered the
  same way for anyone. The PDF and XLSX restricted files are "safe" only because they can't be parsed.
- **The recursive view answers confidently and wrongly.** 5 of 6 `version` questions were answered
  from the stale legacy intranet pages: 5 carry-over days (v3: 3), 10 weeks adoptive leave (12),
  14-character passwords (16), $1,500 learning budget ($2,000), $500 stipend ($600); the sixth (s32)
  was a refusal. The `conflict` question s05 got the retired GlobalConnect VPN. All of these were
  judged **grounded**, because they *are* grounded, in a superseded document.
- `out_of_scope` s15 ("dogs in the office?") was *answered* from a meeting note ("nobody knew if
  there is a policy… Berlin allows it informally").
- `cross_lingual`: the three Arabic pages are indexed, and retrieved **0 of 3** times. English-only
  MiniLM doesn't place them near an English question.
- The deterministic scorer and the 4B judge disagree on s01 ("10 paid sick days": deterministic ✓,
  judge ✗). Task 2's judge–human check needs to look at this.

**Formats the Week 2 loader couldn't read, and what it did with them** (crashed / skipped silently / loaded garbage):

> **Skipped silently, all of them.** As shipped it reads 1 of 191 files (`README.md`), so all 190
> documents are dropped without a warning, an error or a non-zero exit. The startup line even reads
> like success: `Index BUILT: embedded 7 chunks from 1 files`, and `/readyz` reports `"status":"ready"`
> with `"documents": 1`. With a recursive walk, the extension filter still silently drops **72 of 190
> documents**: 23 PDF (every policy, data sheet, manual, SLA and parts catalog), 46 HTML (wiki and
> newsletters), 2 XLSX (error codes, salary bands) and 1 CSV (Cairo holidays). Nothing crashes, and
> nothing loads garbage, because nothing is attempted. Silent skipping, the worst of the three.
> A second trap: pointing `DATA_DIR` at the new corpus while keeping the old `INDEX_PATH` makes the
> incremental index "remove" the 4 Week 1 files and rewrite the Week 2 index in place
> ([evidence](task_01_meet_the_corpus/evidence/loader_behaviour.log)).

### The Week 2 toolchain against the new corpus

| Week 2 tool | Outcome on the new corpus |
|---|---|
| `make check` (green? wall clock?) | **Green, 138 passed** (137 + 1 new gate test). pytest 4.2–5.0 s, **wall 5.5–5.7 s** (3 runs). That's over the 5 s budget, as since Task 8, and unchanged by the corpus. The same run with `DATA_DIR=week3/corpus` is identical (4.2 s), because the fast tier never touches `DATA_DIR`. It stays green and tests **nothing** about the new corpus |
| `make check-live` (which tests failed?) | **Shipped: 3 failed, 5 passed, 1 xpass** (59 s). Failed: `test_grounded_answer_with_citation` and `test_live_stream_delivers_real_model_tokens` (sick days → refusal) and `test_two_turn_follow_up_resolves_pronoun` (turn 1 was a refusal, so "it" was never resolved). `test_awkward_query_triggers_rewrite_loop` **XPASSed**: the loop fires now, because nothing relevant exists. **Recursive: 8 passed + 1 xfail, 4 of them for the wrong reason** (stale legacy handbook, see triage). After the triage below: Week 1 corpus 8 passed + 1 xfail; Week 3 corpus **4 failed** (`check_live_*_after_triage.log`), i.e. red until Task 3 can read the policy PDFs |
| Eval gate: your 30 examples vs `eval_baseline.json` | 38 examples vs the (now archived) baseline 0.921 / 0.974. **Shipped: correctness 0.158, groundedness 1.000, retrieval_hit 0.158**: 29 regressed, cost +66% → **red** ([report](task_01_meet_the_corpus/evidence/w2_gate_report_literal.md)). **Recursive: 0.842 / 0.947 / 0.947, cost +16% → GREEN** (−0.08, exactly at the tolerance; 6 regressed, 2 improved; [report](task_01_meet_the_corpus/evidence/w2_gate_report_recursive.md)). **The green is the alarming result:** the legacy intranet folder is a byte-for-byte copy of the Week 1 corpus, so 15 of 38 expectations are out of date and still "pass". Baseline archived (below) |
| `make cost`: cost per question | Seed set (40, fresh sessions, follow-ups without their history): **shipped $0.000795, 21.2 LLM calls, 4.05 s mean / 4.62 s p95; recursive $0.000668, 18.4 calls, 4.72 s / 7.98 s**. Week 2: $0.000433, 12.8 calls, 3.28 s / 6.89 s. Details in `COST.md` |
| `docker compose up` (starts? loads or rebuilds index?) | **Plain `make up` can't see the new corpus**: compose pins `DATA_DIR=/app/week1/data` in `environment:`, which beats `week1/.env`, and the corpus isn't in the image, so it keeps serving the 4 Week 1 files. With [`docker-compose.corpus.yml`](task_01_meet_the_corpus/docker-compose.corpus.yml) (read-only mount at `/corpus`, `DATA_DIR=/corpus`, `INDEX_PATH=/data/faiss_index_w3`): rebuild + up **167 s, both containers healthy**. First start **builds** a new index: `Index BUILT: embedded 7 chunks from 1 files in 0.28s`. Restart **loads** it (`0 chunks embedded`). `/readyz` is `ready` with `"documents":1`, and a sick-days question is refused after 2 rewrites ([log](task_01_meet_the_corpus/evidence/docker_compose_new_corpus.log)). Image unchanged: 2.07 GB, no new dependencies |

**Baseline archived:** `week2/task_07_eval_gate/eval_baseline.json` → **`eval_baseline_w2.json`**
(renamed with `git mv`, not edited). `check_baseline.py` now refuses that file by name. With no current
baseline it exits 1 with **"NO BASELINE"** instead of comparing against stale numbers. Pinned by
`tests/test_eval_gate.py::test_gate_never_compares_against_the_archived_week2_baseline`. CI's
`eval-gate` job is therefore red (with that reason) until Task 2 commits the v3 baseline.

### Does the rewrite → retry loop fire now? (Week 2 Task 5's question, re-asked)

| Path | Week 2 corpus (from W2 `RESULTS.md`) | Week 3 corpus (seed set) |
|---|---:|---:|
| No rewrite | 18 / 28 (64%) | shipped 0 / 40 (0%) · recursive 16 / 40 (40%) |
| 1 rewrite loop | 2 / 28 (7%) | shipped 0 (0%) · recursive 1 (2%) |
| 2 rewrite loops | 6 / 28 (21%) | **shipped 40 (100%) · recursive 23 (58%)**, every one ending in a refusal |
| Direct (no retrieval) | 2 / 28 (7%) | 0 (0%) · 0 (0%) |

> **Yes, constantly, and it almost never helps.** The loop now fires on **100%** of seed questions
> as shipped (80 rewrites, all triggered by the doc grader rejecting every passage) and **60%** in the
> recursive view (47 rewrites: 34 doc-grader rejections, 13 fact-check rejections), against 29% on
> the Week 2 corpus. In the seed eval **no loop rescued an answer**: all 23 two-rewrite paths ended
> in `refuse`. The only one-rewrite "answer" was the follow-up asked without its history in
> `make cost`, and that answer used the stale handbook. The grader finally has something to
> reject, and it is right to: the answer is in a PDF or HTML page the index doesn't contain. A
> rewritten *query* cannot fix a missing *document*. The loop now mostly turns "I can't read the
> corpus" into 18–21 LLM calls and a refusal (`grade_documents` is 56% of spend). Direct routes
> dropped to 0%, since the seed set has no small talk.

### Week 2 tests and eval examples that failed — triage

Every row with its updated expectation, source document and both runs' scores:
[`w2_eval_triage.jsonl`](task_01_meet_the_corpus/w2_eval_triage.jsonl) (38 examples: 19 unchanged,
**15 world changed**, 3 regression, 1 bad test). The Week 2 `eval_dataset.jsonl` is left as it was,
paired with its archived baseline. Task 2 migrates the examples *from the triage file*. The live
tests were updated in place: their expectations now depend on the configured corpus
(`tests/conftest.py::CORPUS_FACTS`), so the Week 1 corpus keeps its old facts.

| Test or example | Verdict (regression / world changed / bad test) | Reason, and the document that proves it |
|---|---|---|
| Eval #1–#38 on the **shipped** loader: 29 answerable examples → refusal | regression | Ingestion: 0 of 190 documents are indexed (`iterdir()` + extension filter). The expectations aren't the problem |
| `test_grounded_answer_with_citation`, `test_live_stream_delivers_real_model_tokens` (fail as shipped) | regression, **and** world changed (citation) | "10 days" is still true (`policies/hr/HR-POL-005_sick_leave.pdf`), so it's a regression. But the test pinned `employee_handbook.md`, and on the Week 3 corpus that file is a superseded migration copy. Expected source is now HR-POL-005 |
| `test_two_turn_follow_up_resolves_pronoun` (fails as shipped; passes in the recursive view on the stale "5 days") | regression, **and** world changed | Shipped: turn 1 refused, so "it" was never resolved. On the new corpus the right answer is **3 days, used by March 31** (`policies/hr/HR-POL-004_PTO_v3.pdf`, effective 2026-03-01) |
| `test_plausible_sounding_out_of_scope_is_refused` (passes, wrongly) | world changed | No longer out of scope: `policies/hr/HR-POL-011_work_from_abroad.pdf` (2026-04-01) allows up to 30 days a year. Week 3 expectation: answer it, cite HR-POL-011 |
| Eval #2 time off carry rules (C 1→0) | world changed | Reference "5 days" is v2. v3 says 3 days, used by Mar 31 (`HR-POL-004_PTO_v3.pdf`). The new answer is wrong too: it led with the unapproved FTO draft and the 2017 scan (a Task 5 case) |
| Eval #3 time off in first months (C 1→0) | world changed | 90 → **60** days (`HR-POL-004_PTO_v3.pdf`). The answer mixed in the FTO draft |
| Eval #10 meal limit abroad (C 1→0, refused) | world changed | $110 → tier-based **$90 / $55 / $70** (`policies/finance/FIN-POL-002_travel_and_per_diem.pdf`). The refusal itself was caused by the 2019 OCR scan ($80) contradicting $110 |
| Eval #12 expense deadline (C 1→0, refused) | regression | Still 30 days (`policies/finance/FIN-POL-001_expense_reimbursement.pdf`). The 2019 scan's "6O days" contradicted it, and the fact-check rejected a correct answer. Obsolete data now flips correct answers into refusals |
| Eval #20 Figma license (C 0, as in the baseline) | regression (pre-existing) | Same 4B fact-check false negative as in Week 2. Its only source is now `legacy_intranet/it_faq.md`, a superseded page |
| Eval #24 R2 outdoors (G 1→0) | bad test | Correct, cited answer. The self-judging 4B model flipped its groundedness verdict on the same answer. Brittle judging, not a system change. Task 2's judge must differ from the generator |
| Eval #31 R2 limitations (C 1→0) | regression | Retrieval: "R2 is not supported on 5.x" (`product/fleet_manager/release_notes_5.0.md`) outranked the spec sheet. One unrelated "limitation" instead of the three |
| Eval #1, 8, 9, 13, 15, 16, 17, 18, 29, 30, 32, 37 (**pass, on stale facts**) | world changed | 20 PTO days → 20/23/25 by tenure (HR-POL-004 v3); $500 → $600 (HR-POL-010); 10 → 12 weeks (HR-POL-006); $3,000 → $4,000/$3,000 in two instalments (HR-POL-014); $1,500 → $2,000 (HR-POL-016); "immediately" → within 1 hour (IT-STD-009); 14 chars / 180 days → 16, no rotation, MFA (IT-STD-003 v2); GlobalConnect → Northwind Access (IT-STD-007 v3); hotel cap $250 → tier caps (FIN-POL-002); Fleet Manager 4.2 → 4.3 (`release_notes_4.3.md`, `R2_End_of_Life_Notice.md`) |

### Corpus profile

As the Week 2 system sees it after loading (the "shipped" and "recursive" views), plus a reference
extraction of every format for the totals ([profile](task_01_meet_the_corpus/evidence/corpus_profile.md),
[script](task_01_meet_the_corpus/scripts/profile_corpus.py)).

| | Value |
|---|---|
| Documents loaded / total | **0 / 190 as shipped** (plus `README.md`, not a corpus document) · **118 / 190 with a recursive walk** (72 failed: every PDF, HTML, XLSX, CSV, all skipped silently) |
| By source system | drive 113 (106 loadable: 100 meeting notes + md) · wiki 34 (3: the Cairo `.md` pages) · policy-portal 19 (1: the draft `.md`!) · intranet newsletters 16 (0) · intranet-legacy 4 (4) · scanned-archive 4 (4) |
| By format | txt 104 · html 46 · pdf 23 · md 14 · xlsx 2 · csv 1 |
| Languages | English 186, **Arabic 4** (`cairo/`: 3 `.md` + 1 `.csv`, Arabic file names too) |
| Total characters | Shipped: 2,875 (README only). Recursive: 54,962 from 118 documents. All 190, reference extraction: 214,907 (PDFs alone 115,769, 54% of the text, and none of it readable) |
| Total chunks (current settings) | 800/100: shipped **7**, recursive **146**, all 190 extracted **378** (Week 2 corpus: 20) |

The policy portal is the most damaging gap. Of its 19 documents, the only one the Week 2 loader
can read is **`DRAFT_HR-POL-004_PTO_v4_flexible_time_off.md`**, the one that must never be presented
as policy. The approved policies are all PDFs.

### Data-quality issues found (beyond the two in `corpus/README.md`)

Evidence (counts, examples) is in [`corpus_profile.md`](task_01_meet_the_corpus/evidence/corpus_profile.md#data-quality-evidence).
The two known issues, quantified for comparison: the wiki chrome is **57% of the wiki's text**, and
PDF page furniture repeats on 17–23 pages per kind.

| # | Issue | Where | Effect if left alone |
|---|---|---|---|
| 1 | **Superseded copies that look newer than what supersedes them.** The 4 legacy pages are byte-identical to the Week 1 corpus, contradicted by 12 newer policies, but their `last_modified` is the migration date (2026-01-15), later than PTO v2, sick leave and parental leave v2 | `legacy_intranet/*.md` | Any "newest wins" rule picks the stale copy. With the PDFs unreadable it's the *only* version indexed: 5 of 6 `version` answers came from it, and every one was judged **grounded** |
| 2 | **Stale wiki pages contradict the policy portal, with no marker.** Benefits Overview (20 days, 5 carry-over, $1,500, $500), VPN Setup Guide and New Engineer Onboarding (GlobalConnect, retired 2026-06-30), Sales IT Tips (12-char passwords rotated every 90 days; a lost laptop is reported "the next morning", where IT-STD-009 says within 1 hour) | `wiki/people/Benefits_Overview.html`, `wiki/it/VPN_Setup_Guide.html`, `wiki/eng/New_Engineer_Onboarding.html`, `wiki/sales/Sales_IT_Tips.html` | Conflicting chunks for PTO, VPN and password questions. Sales IT Tips gives a **security-relevant wrong answer** (lost device), and its author is a sales rep, not IT |
| 3 | **OCR substitutions and obsolete scans.** 0↔O and 1↔l inside numbers and words (34 suspect tokens: `$5O/day`, `1O days`, `6O days`, `2O17`, `PT0`, `emp1oyees`). 2016–2019 content with `last_modified` = the 2023 scan date, and a cover page claiming "This handbook supersedes all previous versions" | `scanned_archive/*` | Numbers aren't numbers ("$5O" never matches 50), BM25 can't match `PT0` to PTO. When they *are* retrieved they hurt: eval #10 and #12 were refused because the 2019 scan contradicted the current value and the fact-check rejected both |
| 4 | **PDF text artefacts beyond headers and footers:** Unicode ligatures in 20 of 23 PDFs (605 occurrences: `Oﬀ`, `oﬃce`, `ﬁrst`, `Conﬁdential`), and identifiers split across lines (`IT-\nSTD-009`, `FIN-\nPOL-001`, `IT-\nSTD-001`, `NW-BMP-\nRING3`) | `policies/**/*.pdf`, `product/Spare_Parts_Catalog_2026.pdf` | Exact and keyword matching fail on "off", "office", "first" and on policy IDs. `keyword` questions ("what does IT-STD-009 say") can't be found by BM25 even after PDF parsing works, unless text is normalised (NFKC + de-hyphenation) |
| 5 | **Tables flattened to one cell per line.** The travel tier table puts "Germany" in a country list several lines above "$90" and "$260". Same for the PTO tenure table, the SLA plans, the spare parts and the data-classification table | `FIN-POL-002`, `HR-POL-004_PTO_v3`, `Support_SLA_2026`, `Spare_Parts_Catalog_2026`, `IT-STD-001` | Row/column association lives only in line order. A chunk boundary inside a table separates a tier from its amounts, and the model has to guess the columns. This is the whole `table` and `multi_hop` (country → tier → amount) category |
| 6 | **A 23-page manual that is 81% repeated boilerplate:** 1,099 sentences, 204 distinct. The same ~10 safety sentences are reshuffled into every subsection ("Operators must complete…" 83×). The needles (ramp 5°/8°, RESUME held 3 s) are single sentences. It also points to "the light codes table in the appendix", which doesn't exist | `product/R3/R3_Operator_Manual_RevC.pdf` | Dozens of near-identical chunks compete for top-k: "emergency stop" occurs in 20+ boilerplate sentences before §9.2 has the reset procedure. The `long_doc` category, and wasted grader calls on duplicate passages |
| 7 | **Document markings and the ACL disagree, and the ACL doesn't follow the folders.** The R3 manual's footer says "CONFIDENTIAL – for licensed operators only – do not distribute", but its ACL is `all`. The only restricted file outside `hr_restricted/` is a meeting note (`managers`) that names **Project Juniper** (an `hr-leadership` document) and a backfill freeze in hardware sustaining | `product/R3/R3_Operator_Manual_RevC.pdf`, `meetings/2026-09-22_leadership_sync_202.txt` | Folder-based access rules would publish the leadership note to everyone. Even with the ACL enforced, managers learn Juniper exists. Task 6's leak matrix must key on `_metadata.csv` per file and check content, not folders. The confidential manual needs a decision from its owner, not from us |
| 8 | **`last_modified` isn't the content date.** Demo Rover Booking was "last edited 2026-04-15", but it says "R2 demo units were retired in **July 2026**". Legacy pages carry the migration date, scans the scan date | `wiki/sales/Demo_Rover_Booking.html`, `legacy_intranet/*`, `scanned_archive/*` | It can't serve as an effective date or a recency tie-breaker. Task 5 has to use the in-document `Effective date`/`Version`/`Supersedes` fields the policy PDFs carry |
| 9 | **A draft filed as policy, sharing the policy's ID.** The FTO proposal is in `policies/hr/`, ACL `all`, has the newest date of the PTO family (2026-09-18) and calls itself "HR-POL-004 v4.0". Only the file-name prefix and a banner in the body say DRAFT | `policies/hr/DRAFT_HR-POL-004_PTO_v4_flexible_time_off.md` | Version-by-ID or newest-wins logic promotes an unapproved policy ("minimum 15 days, nothing to carry over"). It already happened: eval #2, #3 and #35 quoted it. It's also the only policy-portal file the Week 2 loader can read |
| 10 | **Policy words used in passing, everywhere.** "carry over" appears in 35 of 100 meeting notes (sprint tickets), "PTO" in 53, "VPN" in 38, "password" in 23. Newsletters repeat the same filler ("plan your PTO early for the summer", also in November and March) and contradict each other ("Field Service: 18 consecutive months without a missed SLA" in July 2025, 10 in August, 3 in October) | `meetings/*.txt`, `newsletters/*.html` | BM25 ranks chatter above the policy for the most common HR questions (s15 was answered from a meeting note). The newsletters give contradictory "facts" about the same thing |
| 11 | **Near-identical identifiers and templated rows.** Battery packs `NW-BAT-4380` (R2 only) and `NW-BAT-4830` (R3 only) differ by a transposition. 120 error codes with templated descriptions ("Network timeout" for 6 different codes, "calibration drift" in ~20) | `product/Spare_Parts_Catalog_2026.pdf`, `product/R2/…datasheet.pdf`, `product/Rover_Error_Codes_2026.xlsx` | Dense retrieval can't tell 4380 from 4830, which is a compatibility question with a hardware consequence. Error-code answers must come from exact matching on the code, not semantic similarity |
| 12 | **Encoding and locale.** The Cairo holidays CSV has a UTF-8 BOM (its first header reads `﻿المناسبة`). File names are Arabic. The Cairo Ramadan page allows remote work **4 days a week**, against HR-POL-010's 3, without saying it's a local exception | `cairo/الإجازات_الرسمية_2026.csv`, `cairo/ساعات_العمل_في_رمضان.md` | A naive CSV reader mis-keys the first column. The English-only embedding model retrieved the Arabic pages 0/3 times. The 3-vs-4-day rule is a conflict that needs the asker's office to resolve (a `personalized` + `conflict` case) |

**My guess at the biggest drop — retrieval or generation?** (Task 2 checks this.)

> **Biggest drop: `version` (6 examples).** On the Week 2 gate's categories the biggest drop is
> `factual`, 0.95 → 0.00 as shipped, but that one is just "nothing is indexed". On the seed set,
> `version` is 0/6 in *both* configurations. In the recursive view it fails in the worst way:
> 5 of 6 answers are confident, cited and judged *grounded*, but wrong (5 days, 10 weeks, 14
> characters, $1,500, $500).
>
> **My guess: retrieval, and specifically ingestion, not generation.** Gold documents were indexed
> for 0% of `version` questions (21% across all answerable examples, retrieved 12%, kept by the
> grader 6%). The generator did its job: it faithfully summarised the only, stale, version it was
> given. Groundedness can't catch that, which is why Task 2 needs retrieval metrics against
> `gold_docs`. Generation will matter second: once the PDFs are parsed, both versions will be
> retrieved side by side and the prompt has no notion of "current". That part is Task 5's.
> The two exceptions, where I think generation/model choice is the problem even with perfect
> retrieval: `cross_lingual` (the Arabic pages *were* indexed and never retrieved: the embedding
> model) and `personalized` (needs the user's hire date, which the system doesn't have).

---

## Task 2 — Eval at scale

Measured 2026-11-18 on the laptop GPU. Generator `qwen3.5:4b`; judge `gemma3:4b` (a different model,
as required). Retriever: the production hybrid (BM25 + dense MiniLM). Scripts, review files and every
run: [`task_02_eval_at_scale/`](task_02_eval_at_scale/RUN.md).

**What "the system" is from this task on.** The Week 2 loader indexed only the export's README (Task 1),
so a baseline on it would have been 70 refusals. Every metric, and the judge–human check, would have been
meaningless. I made one small, logged change to the product: when `DATA_DIR` holds a `_metadata.csv`,
`ingest()` indexes the documents listed there, in their sub-folders, keyed by corpus path. It still reads
`.md`/`.txt` only, so **118 of 190** documents load. The other 72 (every PDF, HTML, XLSX, CSV) are now
**skipped with a logged warning**, never silently. Writing parsers for them is Task 3. `DATA_DIR` now
defaults to `week3/corpus`, with its own index (`faiss_index_w3`) so the Week 2 index is never rewritten.
The Docker image still pins the Week 1 corpus until Task 3 mounts the export. Pinned by
`tests/test_corpus_loading.py`.

| | Value |
|---|---|
| Total examples | **100** ([`week3/eval/eval_v3.jsonl`](eval/eval_v3.jsonl), built by [`build_dataset.py`](task_02_eval_at_scale/build_dataset.py); provenance per example in [`dataset_report.md`](task_02_eval_at_scale/dataset_report.md)) |
| From Week 2 (migrated / updated / dropped) | **38 / 21 / 0**. My Week 2 set had 38 examples, not 30, and all 38 are accounted for. 17 migrated with the same expected answer, 21 updated (the 15 Task 1 "world changed" verdicts, plus 6 references made more precise; #37's keyword moved from Fleet Manager 4.2 to 4.3), 0 dropped. Week 2 IDs kept. Category map as in the brief, except where the question now tests a Week 3 behaviour: 5 factual → `version`, #1 → `personalized` (asked by u1002), #10 → `table`, #18 → `conflict`, #22 → `ambiguous` ("the rover" is now two rovers) |
| From the seed set (merged / duplicate of a Week 2 example) | **30 / 10**. s01→#5, s02→#2, s03→#9, s05→#18, s13→#17, s14→#13, s16→#26, s30→#15, s31→#8, s39→#10: Week 2's kept |
| New | **32**: 22 hand-written (conflict, draft, ambiguous, personalized, access, follow-up, multi-hop: categories where the question *is* the design), 10 LLM-generated and reviewed |
| Dev / test split | **70 / 30**. Stratified by category (access also by refuse/answer); every category is in both. Test is frozen: **0 test runs so far** |
| New `eval_baseline.json`: dataset version, date, correctness, groundedness | `northwind-eval-v3` dev, version `5d9544921fd6`, 2026-11-18, **correctness 0.357, groundedness 1.000** (deterministic 0.314, $0.000687/question, 17.9 LLM calls). Two runs, identical verdict for verdict. Tolerance 0.08 kept ([justification](task_02_eval_at_scale/tolerance_justification_v3.md)) |
| Synthetic candidates generated / accepted / rejected | **65 / 10 / 55** (15% accepted; 19% if "valid, but its category was already full" isn't counted as a quality rejection). [Review of every candidate](task_02_eval_at_scale/synth/candidates_reviewed.jsonl) |
| Top 3 rejection reasons | 1. **Boilerplate (21):** questions about the ~10 safety sentences the R3 manual repeats 80+ times ("slows to 0.5 m/s", "operator course"), not about its needles. 2. **Valid, but the category was already full (13).** 3. **Duplicate of an existing example (9).** Then: malformed or ambiguous (5), templated filler rows of the error sheet (4), **wrong or hallucinated answers (3)**: Egypt's meal allowance read from the hotel-cap column of a flattened table, a "one operator at a time" rule that isn't in the text, and the 24-hour visitor rule pinned on Cairo |
| Judge model / generator model | `gemma3:4b` / `qwen3.5:4b` (synthetic candidates also by `qwen3.5:4b`) |
| Judge–human agreement (20 examples) | **18 / 20 (90%)** with the final judge prompt; 17 / 20 (85%) with Week 2's prompt. ⚠️ The "human" labels were made by the coding assistant on the intern's behalf, against the reference and the source document, and are **awaiting the intern's review** ([`human_labels.json`](task_02_eval_at_scale/human_labels.json)) |
| Retrieval-only eval: wall clock / cost | **7.5 s** for `make eval-retrieval` end to end (5.6 s loading the embedding model and index; 60 queries 0.3 s, p50 3 ms) / **$0** (local; 731 query tokens = $0.000015 at text-embedding-3-small) |

### Retrieval by category (dev)

Document-level, from the retriever alone (`make eval-retrieval`; the production hybrid at depth 10 per
retriever). Follow-ups query with the earlier user turn prepended, a deterministic stand-in for the
`contextualize` LLM call. `user_id` is passed through but not used yet (Task 6).

| Category | n | R@1 | R@3 | R@5 | R@10 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| factual | 10 | 0.10 | 0.10 | 0.10 | 0.10 | 0.10 |
| table | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| keyword | 4 | 0.00 | 0.25 | 0.25 | 0.25 | 0.08 |
| version | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| conflict | 3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| draft | 4 | 0.25 | 0.75 | **1.00** | 1.00 | 0.55 |
| multi_hop | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| multi_part | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ambiguous | 3 | 0.00 | 0.33 | 0.33 | 0.33 | 0.17 |
| long_doc | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| cross_lingual | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| follow_up | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| personalized | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| access *(authorised users only)* | 3 | 0.00 | 0.33 | 0.33 | 0.33 | 0.17 |
| **All** | 60 | **0.03** | **0.12** | **0.13** | **0.13** | **0.08** |

**The ceiling explains most of it:** only **13 of the 60** answerable dev questions have *any* gold
document the loader can read. The rest are PDF, HTML or XLSX. Of those 13, retrieval finds **8**. Three of
the 5 misses are `cross_lingual`: the Arabic pages are indexed (3 of 4 gold docs) and never retrieved,
because the embedding model is English-only. So 47 of 52 retrieval misses are ingestion (Task 3), and the
rest are the embedding model (Task 4).

### Generation by category (dev)

Full pipeline, then the judge (`make eval`). These are the committed baseline's numbers; runs 2 and 3
were identical.

| Category | n | Deterministic | Correctness | Groundedness |
|---|---:|---:|---:|---:|
| factual | 10 | 0.70 | 0.70 | 1.00 |
| table | 4 | 0.00 | 0.00 | 1.00 |
| keyword | 4 | 0.50 | 0.50 | 1.00 |
| version | 5 | 0.00 | 0.00 | 1.00 |
| conflict | 3 | 0.00 | 0.00 | 1.00 |
| draft | 4 | 0.50 | 0.50 | 1.00 |
| multi_hop | 4 | 0.00 | 0.25 | 1.00 |
| multi_part | 4 | 0.00 | 0.25 | 1.00 |
| ambiguous | 3 | 0.33 | 0.67 | 1.00 |
| long_doc | 4 | 0.00 | 0.00 | 1.00 |
| cross_lingual | 4 | 0.00 | 0.00 | 1.00 |
| follow_up | 4 | 0.25 | 0.25 | 1.00 |
| personalized | 4 | 0.00 | 0.00 | 1.00 |
| access | 7 | 0.43 | 0.43 | 1.00 |
| out_of_scope | 6 | 1.00 | 1.00 | 1.00 |
| **All** | 70 | **0.31** | **0.36** | **1.00** |

- **Two leaks on dev:** n28 gave the 3.5% merit budget (an `hr` document) to u1002, a Support Engineer,
  and s20 described Project Juniper ("18 roles") to u1001. The Week 2 system has no notion of a user;
  Task 6 fixes this. Both are deterministic failures (`must_not_include`), so the gate sees them.
- 32 of 70 answers are refusals. Every `out_of_scope` question is correctly refused, but so are 4 of 4
  `cross_lingual`, 3 of 4 `table` and 3 of 4 `long_doc` questions.
- **Groundedness is 1.00 everywhere, and that is a judge limitation, not a property of the system.** 32
  answers are refusals, which count as grounded by rule, and `gemma3:4b` said YES to all 38 others,
  including stale answers (grounded in a stale document, fairly) and two wrong-number answers. On 6
  probes it caught **1 of 3** planted unsupported claims (`judge_check.py`). A stricter groundedness
  prompt scored the same 4/6 with different mistakes, so I kept the existing one. The groundedness gate
  can't catch much until the judge is stronger (an 8B judge needs a ~5 GB download: your call).
- **Judge prompt changed.** Week 2's correctness prompt, run on `gemma3:4b`, called "90 days" correct
  against "60 days" and invented facts the answer didn't state. The new prompt makes the judge quote the
  answer's value for each key fact and fail any mismatch. Same answers, re-judged: human agreement
  16–17/20 → 18/20, agreement with the deterministic floor 58–59/70 → 62–63/70
  ([`judge_check.json`](task_02_eval_at_scale/evidence/judge_check.json)). Replaying the judge on
  identical answers moves at most 1 of 70 verdicts, so it is not perfectly deterministic.

**Judge–human disagreements** (final judge = the baseline's verdicts; same answers as the labelled run):

| Example | Judge said | I said | Who was right, and why |
|---|---|---|---|
| #29 referral bonus + new hire's PTO | correct | incorrect | **Me.** The answer gives the stale facts: "$3,000 after 90 days" and "PTO not usable for the first 90 days". HR-POL-014 v2.0 pays $4,000/$3,000 in two halves (90 days and 12 months), and HR-POL-004 v3.0 says 60 days. The judge still accepts a number that differs from the reference when the answer *sounds* complete |
| #13 referral bonus amount and timing | correct | incorrect | **Me.** Same stale $3,000 single payment. The reference lists $4,000, $3,000, 90 days and 12 months; the answer has two of the four, and $3,000 is right only for non-engineering roles |
| *(Week 2 prompt only)* #18 VPN | correct | incorrect | **Me.** It told the user to install GlobalConnect, which IT-STD-007 v3.0 retired. Fixed by the stricter prompt |
| *(Week 2 prompt only)* n20 battery | correct | incorrect | **Me.** One battery (no part number) for an ambiguous "the rover". Fixed by the stricter prompt |

In the 20 labelled examples every disagreement is the judge being **too lenient**, and the
deterministic scorer catches all four. Outside the sample the stricter prompt can also err the other
way: n10 ("by October 31, 2026", correct) was judged incorrect, apparently for leaving out the comment
address. That's why both scores are reported. They disagree on 7 of 70 dev examples.

**Was the Task 1 guess right?**

> **Yes.** Task 1 guessed `version` was the biggest drop and that it's retrieval, specifically ingestion.
> On dev, `version` has **recall@5 0.00 and a pass rate of 0.00** (deterministic and correctness):
> low recall, low pass rate. The ceiling makes it certain: none of the 5 `version` questions has a gold
> document the loader can read (they are all policy PDFs), so the generator only ever sees the stale
> legacy copy and repeats it. Wednesday's retriever work can't fix that; Task 3's parsers have to come first.
>
> Two categories break the pattern, and they're worth knowing before Wednesday:
> - **`draft`: recall@5 1.00, pass 0.50: mostly a generation problem.** The draft is always retrieved.
>   n09 presented the unapproved FTO proposal as policy ("every employee is expected to take a minimum
>   of 15 days"), which is Task 5's. n11 refused because the policy that answers it (PTO v3) is an
>   unreadable PDF, and only the draft was there to contradict.
> - **`cross_lingual`: the gold doc is indexed, recall 0.00: retrieval, but the embedding model, not ingestion.**
>   That is a Task 4 experiment (a multilingual embedding model).

---

## Task 3 — Ingestion

Measured 2026-11-18. One loader per format in [`ingest/`](../ingest/) (PDF tables rebuilt as rows with
their column names, page furniture and wiki chrome removed, spreadsheet rows keeping their headers,
NFKC, OCR repair, metadata parsed from the text, the manual's repeated sentences dropped), plugged
into the capstone's incremental `ingest()`. Why each format looks the way it does:
[`task_03_ingestion/LOADERS.md`](task_03_ingestion/LOADERS.md). The hypothesis was committed before
any code ([`EXPERIMENTS.md` ING-01](EXPERIMENTS.md#task-3--ing-01-ingestion-that-reads-every-format)).

| | Before | After |
|---|---:|---:|
| Documents loaded | 118 / 190 (`.md`/`.txt` only) | **190 / 190** |
| Documents skipped (with reasons listed below) | 72 (every PDF, HTML, XLSX, CSV; logged since Task 2) | **0** |
| Chunks | 139 | **348** (1 per spreadsheet/CSV row: 132; the 23-page manual: 6) |
| Duplicates detected | — | **1 near-duplicate document** (a mirror), **0 exact duplicate chunks** across documents, **1,064 repeated sentences** removed within the manual |
| recall@5, all (dev) | 0.133 | **0.917** (MRR 0.076 → 0.612) |

recall@5 by category, before → after. Retrieval is deterministic: two runs gave identical rankings for
all 60 examples, so the noise floor is 0 and every move below is real. `draft` (1.00 → 1.00) is the
only category that didn't move.

| Category | Before | After |
|---|---:|---:|
| factual | 0.10 | 1.00 |
| table | 0.00 | 1.00 |
| keyword | 0.25 | 1.00 |
| version | 0.00 | 1.00 |
| conflict | 0.00 | 1.00 |
| multi_hop | 0.00 | 1.00 |
| multi_part | 0.00 | 0.75 |
| ambiguous | 0.33 | 1.00 |
| long_doc | 0.00 | 1.00 |
| cross_lingual | 0.00 | 0.25 |
| follow_up | 0.00 | 1.00 |
| personalized | 0.00 | 0.75 |
| access *(authorised users only)* | 0.33 | 1.00 |

The 5 dev questions still missed at recall@5:
- **4 are the Arabic pages** (n15, n16, s25, n26). The English-only MiniLM embedding model doesn't
  place them near English questions. That's a Task 4 experiment (a multilingual embedding model),
  not ingestion.
- **#17 "What are the password rules?":** three meeting notes about a "password reset flow" outrank
  IT-STD-003. That's the lexical trap from Task 1 issue #10.

**What the answers did** (full pipeline, dev, two identical runs;
[evidence](task_03_ingestion/evidence/dev_full_after.json)):
- **Scores:** deterministic **0.314 → 0.743**, correctness 0.357 → 0.500, groundedness 1.000 → 0.986.
- **Cheaper per question:** refusals fell from 32 to 15 of 70 and the rewrite loop fires on 20 instead
  of 40, so LLM calls per question fell from 17.9 to 13.9.
- **Live tier on the Week 3 corpus:** 8 passed + 1 xfail. The four Task 1 "world changed" tests pass:
  HR-POL-005 cited, 3-day carry-over, work from abroad answered from HR-POL-011.
- **The gate:** passes against the Task 2 baseline. `eval_baseline.json` is **re-set on this system**
  (correctness 0.500, groundedness 0.986, deterministic 0.743,
  [justification](task_03_ingestion/tolerance_justification.md)).

Two consequences to know about:
- ⚠️ **Leaks went from 2 to 4 on dev.** The salary bands (XLSX) and the disciplinary procedure (PDF) are
  now readable, so u1001 gets the L4 salary range (s18) and the PIP length (s22). Restricted content is
  now *more* exposed until Task 6. The service must stay on this machine until then.
- **The correctness judge is now too strict on correct answers.** On 18 dev examples the deterministic
  check passes and the judge says incorrect.
  - **About 13 are plainly correct** (#4, n04, #15, s32, n10, n11, n13, s10, n17, n22, …): the judge
    penalises reference details the question didn't ask for, like "8 degrees unloaded".
  - **About 5 are rightly failed:** s28 and n25 list every tenure band instead of the user's, which games
    `must_include`; s29 repeats the stale sales-wiki advice; #12 mixes in the 2019 scan.
  - **Cause:** Task 2's stricter prompt was tuned on a system whose answers were mostly wrong. On correct
    answers it overshoots. Recalibrating it needs new human labels on this system's answers: a follow-up,
    deliberately not mixed into the ingestion change. Until then, the deterministic score is the more
    honest number.

**Dedup policy, and why:**

> **Three kinds of duplicate, three policies**
> ([`ingest/dedup.py`](../ingest/dedup.py), [LOADERS.md § Deduplication](task_03_ingestion/LOADERS.md#deduplication)):
>
> 1. **Repeated sentences within a document** are **removed** at parse time (first occurrence kept):
>    1,064 of the R3 manual's 1,099 sentences. That's what took `long_doc` from 0.00 to 1.00.
> 2. **Exact duplicate chunks across documents** (sha1 of the normalised body): keep the most
>    authoritative, label the others. **0 found**, checked on every ingest.
> 3. **Near-duplicate documents across source systems** (containment of word 3-shingles ≥ 0.75, or a
>    declared mirror) are **kept and labelled** `duplicate_of` the document from the more authoritative
>    source. **1 found:** `wiki/it/Password_Policy.html` → IT-STD-003 (containment 0.759; the page says
>    "This page mirrors IT-STD-003 v2.0").
>
> **Why label instead of delete.**
> - A copy is a ranking question: it agrees with the original until it goes stale, and stale versions
>   are Task 5's.
> - Deleting it at ingest would tie one document's index content to another's, so editing IT-STD-003
>   would have to re-ingest the wiki. That breaks per-document incremental ingest. Labelling runs over
>   stored texts after every ingest in 0.02 s, with no embedding call.
>
> **Deliberately *not* duplicates.** The highest similarity scores in the corpus come from documents of
> the *same* source sharing a template: team pages up to 0.79, newsletters 0.80, meetings 0.74. They
> share filler, not facts; merging them would delete "Karim is on PTO next week" because "Sofia is on
> PTO next week" exists.

**Incremental-index + cache-invalidation test:** `tests/test_corpus_loading.py::test_changing_one_document_reembeds_only_it_and_invalidates_cached_answers`

- **The setup:** an export in three formats (Markdown, HTML, CSV with a BOM, in sub-folders), counting
  embeddings, and the real API with its answer cache.
- **Editing one file:** only that file's chunks are embedded (counted), the other two are reused, and an
  answer cached before the edit is not served.
- **Removing a file:** nothing is embedded, its vectors are deleted, and the cache is invalidated again.
- **`/readyz`:** the same test checks it reports the snapshot, document counts and build time.
- **Timing:** fast tier, fake embeddings, 0.14 s. The Week 2 invalidation tests (`test_cache.py`, add
  and change) still pass.

**Warm `docker compose up` startup log line** (must say "loaded"). Compose now mounts `week3/corpus`
read-only at `/corpus`; the index lives on the named volume at `/data/faiss_index_w3`
([log](task_03_ingestion/evidence/docker_compose_up.log)):

```
api-1  | 2026-11-18 11:02:33,848 INFO northwind: Index LOADED from /data/faiss_index_w3 in 0.20s: 348 chunks from 190 files, 0 chunks embedded
{"status":"ready","graph_compiled":true,"index":"loaded","chunks":348,"documents":190,"retriever":"hybrid (BM25 + dense)","active_sessions":0,"startup_seconds":11.07,"corpus_snapshot":"2026-10-01","documents_skipped":0,"index_built_at":"2026-11-18T11:01:41+00:00","index_build_seconds":27.18,"index_updated_at":"2026-11-18T11:01:41+00:00"}
```

The first `up` on that volume logged `Index settings changed (…all-MiniLM-L6-v2 -> …/w3-loaders-1):
rebuilding`, then `Index BUILT: embedded 348 chunks from 190 files in 27.19s`. The loader version in
the index signature is what forced it. Writing to `/corpus` inside the container fails: `Read-only file system`.
Every ingest also writes a JSON log line in the request-log format:

```
{"event": "ingest", "level": "info", "ts": "2026-11-18T11:02:06.779Z", "corpus": "/corpus", "snapshot": "2026-10-01", "documents_loaded": 190, "documents_skipped": 0, "chunks": 348, "duplicates": 1, "added": 0, "changed": 0, "removed": 0, "reused": 190, "rebuilt": false, "embedding_calls": 0, "duration_s": 0.2, "corpus_version": "d2a735e0ebf4e2bf"}
```

**`make check` wall clock after Task 3's tests:** pytest **4.4–5.4 s** over 5 runs (152 tests,
typically 4.5 s), so at the budget rather than comfortably under it, as before this task (4.1–5.2 s
in Task 2). Wall clock including ruff: 5.6–7.0 s. To stay there, the tests that parse real policy PDFs
and the whole corpus are marked `corpus`, since PyMuPDF's table finder costs ~0.2 s a page. They run in
`make check-corpus` (4.8–8.6 s) and in CI's fast job, which runs everything except `live`. The fast tier
keeps a synthetic PDF built in milliseconds, plus unit tests of the table-row merging on the rows those
PDFs really produce.

**Skipped documents and reasons:**

> **None: 190 of 190 load** ([ingestion report](task_03_ingestion/evidence/ingestion_report.json)).
> The mechanism is tested: a corrupt PDF or a document listed in `_metadata.csv` but missing on disk is
> skipped with its reason. The reason goes in the stats, in a warning, in `ingestion_report.json` and as
> an `ingest_document_skipped` JSON log line
> (`tests/test_corpus_loading.py::test_export_is_indexed_from_metadata_and_every_skip_is_listed`).
> The export's own `README.md`, `_metadata.csv` and `_directory.csv` are not documents and are never
> indexed.

**Also changed for the container:** the image gains PyMuPDF, openpyxl and BeautifulSoup. Measured delta
for the full API image: **+285 MB (2.07 → 2.35 GB)**. Most of it is PyMuPDF 2.1 itself (110 MB) and
onnxruntime (63 MB), which PyMuPDF 2.x's new `pymupdf_layout` pulls in. Pinning PyMuPDF 1.x would
probably save over 100 MB, but it means re-validating every loader: a follow-up.

---

## Task 4 — Retrieval experiments

*(Every experiment is in `EXPERIMENTS.md`. This section is the outcome.)*

| | Baseline | Winner |
|---|---:|---:|
| Config summary | | |
| recall@5 dev | | |
| recall@5 **test** (run once) | | |
| MRR dev | | |
| MRR **test** | | |
| Latency per query | | |

**Why this winner, citing per-category numbers:**

>

**Did test agree with dev?**

>

**CI retrieval gate tolerance, and how it was derived from the noise floor:**

>

---

## Task 5 — Time and truth

| Category | Before (dev) | After (dev) |
|---|---:|---:|
| version | | |
| conflict | | |
| draft | | |
| ambiguous | | |

**Time-travel test:** `tests/___::___` — with `AS_OF_DATE=2026-02-15`: ___ days.
With the default date: ___ days.

**Source authority order** (highest first, with one sentence of justification each):

1.
2.
3.
4.
5.
6.

**Ambiguity policy** (clarify, or answer every reading?), and the test that pins it:

>

---

## Task 6 — Who's asking

| Test | Name | Passes |
|---|---|---|
| Leak matrix (6 users × restricted docs) | `tests/___::___` | ☐ |
| Cache scope | `tests/___::___` | ☐ |
| Session binding (403) | `tests/___::___` | ☐ |
| Unknown user (401) | `tests/___::___` | ☐ |

**`access` category on dev:** leaks: ___ · authorised users answered: ___ / ___

**New rows for the Week 2 degradation table:**

| Failure | Behaviour | Tested by |
|---|---|---|
| Directory file missing or unreadable | | |
| Unknown `user_id` | | |
| Chunk with no ACL metadata | | |

**Rate limit keyed by `user_id`:** `tests/___::___`

**`make check` wall clock with the leak matrix:** ___ s (budget 5 s) · CI: ___ s (budget 60 s)

**Injection attempts** (outcome with the Week 2 injection check on / off):

| # | User | Attempt | Outcome (check on) | Outcome (check off) |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

**Why filtering after retrieval isn't good enough:**

>

---

## Friday — Holdout

| | Deterministic pass rate | Leaks |
|---|---:|---:|
| Dev | | |
| Test | | |
| Holdout | | |

**Gap by category (test → holdout), largest first:**

| Category | Test | Holdout | Gap |
|---|---:|---:|---:|
| | | | |

**Three holdout failures, diagnosed:**

| Holdout ID | Category | Retrieval or generation? | Evidence |
|---|---|---|---|
| | | | |
| | | | |
| | | | |

### Release v1.1

- [ ] Holdout ran against a clean-clone `docker compose up` of `v1.1-rc`
- [ ] Tagged `v1.1`
- [ ] `CHANGELOG.md` v1.1 entry
- [ ] `ARCHITECTURE.md` updated (diagram included)
- [ ] `RUNBOOK.md`: re-ingest, suspected-leak response, gate red on new baseline
- [ ] `docs/RFC-001-actions.md` reviewed

**The weakest category now, its number, and whether it's retrieval or generation:**

>
