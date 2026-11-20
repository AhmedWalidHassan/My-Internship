# Time and truth: how the assistant picks the current, approved source

The brief is in [README.md](README.md). The code is in
[`week1/common/truth.py`](../../week1/common/truth.py) (product code, as the Week 3 README requires). The
numbers are in [`week3/RESULTS.md`](../RESULTS.md#task-5--time-and-truth) and
[`week3/COST.md`](../COST.md#task-5--time-and-truth). The experiment log (TT-01, TT-02, hypotheses
committed first) is in [`week3/EXPERIMENTS.md`](../EXPERIMENTS.md).

## What happens to a question

1. **`retrieve`** (no LLM): the hybrid retriever's passages go through `curate()`.
   - **Label.** Each passage is labelled against `AS_OF_DATE` (default 2026-10-01, the snapshot date):
     - `CURRENT`: approved, the latest effective version on or before the date.
     - `NOT_YET_IN_EFFECT`: effective after the date.
     - `SUPERSEDED`: a newer approved version is in force.
     - `DRAFT`.
     - Otherwise, by the authority order below: `AUTHORITATIVE`, `LOWER_AUTHORITY` or `OUTDATED`.
   - **Swap.** A superseded version that was retrieved without its current version brings the current
     one in, from a catalog of every version in the index.
   - **Drop.** Superseded versions are removed. So are legacy intranet copies and scans on the same
     topic as a current passage.
   - **Add the draft** of a document being answered from, when the question uses the draft's own terms
     ("flexible time off").
   - **Order:** authority first, drafts and not-yet-effective versions last.
   - **Ambiguity:** "the rover" with no R2/R3 named, while the passages cover both, adds an
     "answer for both" note.
2. **`grade_documents`** (unchanged, one LLM call per passage), plus one rule with no LLM call: if the
   grader kept a lower-authority page but dropped the current policy on the same topic, the policy comes
   back. Without it, "the sales IT tips say 12 characters, is that right?" was answered from the wiki
   alone.
3. **`generate`** sees `[file | status label] passage`. New rules: take the rule from CURRENT passages
   and name the version ("Under HR-POL-004 v3.0, effective 2026-03-01, …"), mention a draft only as a
   proposal, say when a lower-authority source is out of date, and answer every reading of an ambiguous
   question.
4. **`grade_generation`** (the fact-check) is unchanged. TT-02 tried to let it read the labels, so that
   "the wiki page is out of date" counts as supported. That fixed `draft` but traded 2 answers for 4
   new refusals, and it would have loosened the eval's groundedness judge, which shares the prompt. It
   was reverted (EXPERIMENTS.md).

## Source authority order

Highest first. It applies when two sources disagree and neither says it replaces the other. Between
versions of the same document, the effective date decides, not this order.

| Level | Sources | Why |
|---:|---|---|
| 1 | **Approved policies** (`policies/`: policy portal) | The controlled, versioned system of record: every document has an ID, a version, an effective date and an approval status |
| 2 | **Product and owner documentation** (`product/`, `hr_restricted/`) | Written and maintained by the team that owns the thing it describes (data sheets, manuals, SLA, parts, HR guidance), but not versioned by the policy process |
| 3 | **Wiki** (`wiki/`, `cairo/`) | Maintained but unversioned and editable by anyone, so it lags policy changes (VPN Setup Guide, Benefits Overview, Sales IT tips) or only mirrors a policy |
| 4 | **Newsletters** (`newsletters/`) | Dated announcements that summarise a change once: accurate on the day, never updated |
| 5 | **Meeting notes** (`meetings/`) | Mention rules in passing, without authority or follow-up |
| 6 | **Legacy intranet and scanned archive** (`legacy_intranet/`, `scanned_archive/`) | The 2024 intranet migrated as-is and OCR scans from 2016–2019: superseded wherever the policy portal covers the topic |
| – | **Drafts** (any level) | Never the rule. Shown last, labelled "a proposal that is NOT approved policy" |

**A local exception doesn't follow this order.** The Cairo office's Ramadan page (level 3) allows 4
remote days, against HR-POL-010's 3 (level 1). The more specific rule applies to Cairo staff, so both
are shown, with the conflict named (dev n07). Ordering by authority isn't enough here. It is noted, not
solved: it needs the asker's office (Task 6).

## Ambiguity policy: answer every reading

When a question has more than one reading that the documents answer differently ("the rover" = R2 or
R3), the assistant **answers for each reading, labelled**, and never picks one silently. It doesn't ask
a clarifying question. Why:
- Here the readings are few (two rovers, two parental-leave cases) and each answer is a line long.
  Answering both costs a few tokens; asking back costs the user a full round trip (≈ 5–6 s plus their
  typing) on a question they may have meant broadly.
- A clarifying question also breaks the one-shot API contract (`/chat` returns an answer, not a
  question) and every `ambiguous` example's expectation (both readings in `must_include`).
- For "the rover" the detection is deterministic: `truth.ambiguity_note()`. For other kinds of
  ambiguity (parental leave: birth vs adoptive; hotel caps by tier), generator rule 9 asks for every
  reading.

Pinned by `tests/test_truth.py::test_ambiguity_policy_answers_every_reading_never_one_silently`.
Live: "What is the payload capacity of the rover?" → "R2: 80 kg. R3: 120 kg."

## Where supersession is decided, and what it costs

**Retrieval time, from metadata**, in the graph's `retrieve` node, before any LLM call.

- **Not at ingestion.** Filtering superseded chunks out of the index would make "current" a property
  of the index rather than of the question's date: the time-travel test (`AS_OF_DATE=2026-02-15` → v2.0,
  5 days) would need a different index. Ingestion still does the hard part: parsing `doc_id`,
  `version`, `status` and `effective_date` (Task 3), which this step reads.
- **Not at generation alone.** Letting the 4B model see every version and choose relies on it reading
  dates and statuses right every time. In Task 3/4 runs it didn't: it answered "it depends on the
  version" (#3) and presented PTO v3 as "switching to flexible time off" (n08).
- **What it costs:**
  - **Metadata quality.** Supersession is only as good as the parsed `doc_id`/`effective_date`. A copy
    that doesn't carry its ID (the legacy handbook "Employee Handbook 2024, section 2", superseded by
    HR-POL-004 v2.0) is handled by the authority order and a word-overlap test, not by version logic.
  - **Heuristic topic tests.** "Same topic" uses word-overlap thresholds (0.18 to drop a legacy copy,
    0.07 to restore a dropped policy) chosen on a handful of pairs from this corpus. That may not
    generalise to the holdout.
  - **The model still has to follow the labels.** It usually does, but a label can be ignored.
  - **Dropping superseded passages has a price.** With the default date, an answer can't say "it used
    to be 5 days" unless the current version says so itself (HR-POL-004 v3.0 does, in its transition rule).
  - **Runtime cost:** **no extra LLM call**, but longer prompts. See `COST.md`.

## Structured citations (API change)

`ChatResponse.sources` and the stream's `done.sources` were `list[str]` (`"file.md › Section"`). They are
now objects: `{path, title, doc_id, version, effective_date, section, status}`. **This breaks clients that
joined or displayed the strings.** The bundled Streamlit UI renders them as
"Paid Time Off Policy (HR-POL-004 v3.0, effective 2026-03-01) › 3. Carry-over" and still accepts plain
strings from an older API. The request log line gains `cited_versions` (`["HR-POL-004 v3.0"]`). The
answer cache stores the objects; entries cached in the old format don't survive a restart anyway
(the cache is in memory).

## Reproduce

```bash
make check                                                   # tests/test_truth.py: time travel, drafts, authority, ambiguity
python week3/task_05_time_and_truth/scripts/live_check.py    # real model, default AS_OF_DATE
AS_OF_DATE=2026-02-15 python week3/task_05_time_and_truth/scripts/live_check.py "How many PTO days can I carry over into next year?"
make eval                                                    # dev before/after
```
