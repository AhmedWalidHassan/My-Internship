# Ingestion: what a good chunk looks like, per format

The code is in [`ingest/`](../../ingest/) at the repo root (the Week 3 README puts product code in
`ingest/`, not in task folders). The capstone's incremental `ingest()` calls it for every document
of a corpus export. Tests: [`tests/test_ingest.py`](../../tests/test_ingest.py) (loaders) and
[`tests/test_corpus_loading.py`](../../tests/test_corpus_loading.py) (incremental re-ingest, skips,
cache invalidation, `/readyz`).

**Rules for every chunk:**
- **Context line.** It starts with "`<title> [<id> v<version> · <status> · effective <date>] › <section>`",
  so a passage still says which document and which version it came from after it is cut out. For
  example, `Paid Time Off Policy [HR-POL-004 v3.0 · Approved · effective 2026-03-01] › 3. Carry-over`.
  A draft says `DRAFT, not approved` in that line, in every one of its chunks.
- **Packing.** Whole sections are packed up to `CHUNK_SIZE` (800). Only a longer section is split, with overlap.
- **Text normalisation.** Unicode NFKC turns `Oﬀ` into `Off`, then identifiers broken at their hyphen are
  re-joined (`IT-\nSTD-009` → `IT-STD-009`). NFKC leaves the corpus's Arabic text byte-identical to NFC
  (tested).
- **Language.** Recorded per chunk by script share (`ar`/`en`): the corpus has exactly these two, and a
  script test is deterministic, unlike `langdetect` without a fixed seed.

## Per format

| Format | n | What a chunk is | Why |
|---|---:|---|---|
| **PDF** (policies, data sheets, SLA, parts catalog, manual) | 23 | Sections are split on the 15 pt bold headings, and tables become one line per row, each cell carrying its column name: `Tier: B \| Countries: Egypt, India, … \| Meals per day: $55 \| Hotel cap per night: $150`. Key/value tables (the data sheets) become `Ingress protection: IP54 - indoor use only` | Plain extraction prints one cell per line, so "Germany" and "$260" end up 4 lines apart with nothing tying them. With the row rebuilt, the answer is in one line. Tables are found with PyMuPDF `find_tables()`, but the cell text is re-read with `get_text(clip=cell)` because the table extractor drops spaces ("UnitedStates", "30." for 3.0). Wrapped cells come back as extra rows and are merged (`_merge_rows`: travel tiers, `NW-BMP-` + `RING3`, "Ingress"+"protection", "Premium Plus"+"(new in 2026)") |
| | | **Removed:** page furniture, i.e. every 7 pt line in the top and bottom margins ("Northwind Robotics Policy Portal \| Controlled copy…", "… - Page 7 of 23"). Kept: the classification marking, as metadata (`INTERNAL`, `CONFIDENTIAL - for licensed operators only…`, `RESTRICTED - HR and people managers only`), and real information in a footer ("Prices exclude tax and shipping") | The font size alone identifies furniture in this export (7 pt, always in the margins), so no per-document pattern list is needed. Sentences cut by a page break are re-joined |
| | | **Header block → metadata:** Document ID, Version, Status, Effective date, Owner, Supersedes. When PyMuPDF doesn't see the block as a table (5 of the 19 policies), it is parsed from the leading lines instead | These are the fields Task 5 needs. All 19 policy PDFs get all four (`doc_id`, `version`, `status`, `effective_date`) |
| | | **The 23-page manual:** a sentence already said earlier in the document is dropped (first occurrence kept). 1,064 of 1,099 sentences go, the needles stay (`press and hold the blue RESUME button for 3 seconds`, `maximum ramp incline is 5 degrees…`), and 23 pages become 6 chunks | 81% of the manual was the same ~10 safety sentences, reshuffled into every subsection (Task 1 issue #6). Only documents over 20,000 characters are checked, so short documents that repeat a phrase on purpose are untouched |
| **HTML** (wiki, newsletters) | 46 | The `.content` element only. `.nav`, `.sidebar`, `.footer` and the newsletter's unsubscribe line are dropped, `<h2>` starts a section, list items keep their `- `. The footer's "Last edited by X on DATE" becomes `content_date`/`edited_by`, a newsletter's issue becomes `content_date`, and "This page mirrors IT-STD-003 v2.0" becomes `mirrors` | The chrome was 57% of the wiki's text (39% of the Password Policy page). Every page had the same nav words, which matched every query a little |
| **XLSX** (error codes, salary bands) | 2 | **One row per chunk**, every value with its column name: `Code: E-217 \| Subsystem: Drive \| Description: Left drive motor overcurrent \| Severity: High \| Operator action: … \| Applies to: R2, R3`. A one-column sheet ("Read me", "Notes") is plain text | A row means nothing without its headers. Error-code questions are exact-match lookups, and a 120-row block chunked by size would bury `E-217` among 10 other codes. A row on its own gives BM25 an exact, short target |
| **CSV** (Cairo holidays) | 1 | One row per chunk with its headers: `المناسبة: عيد الفطر \| التاريخ: 2026-03-20 \| عدد الأيام: 3`. Read as `utf-8-sig` | Same reasoning as XLSX. The UTF-8 BOM would otherwise end up inside the first header (Task 1 issue #12) |
| **Markdown** (legacy intranet, draft, release notes, Cairo pages, restricted HR) | 14 | `#` = title, `##`… = sections, Markdown tables become header-carrying rows (R2 end-of-life milestones). Parsed: `status: draft` (from the "DRAFT … NOT APPROVED" banner, not from the folder or file name), `doc_id`/`version` from "(proposed HR-POL-004 v4.0)", `proposed_effective_date` (deliberately **not** `effective_date`), release-note version and month, and the RESTRICTED / "managers only" marking in a title | Section-aligned, as in Weeks 1–2. A draft's proposed date must never pass for an effective date (Task 5) |
| **Text** (meeting notes, scans) | 104 | Title line, then `Notes`/`Action items` sections. `Date:` becomes `content_date`. **Scans** are OCR-repaired: inside numbers O→0 and l/I→1 (`$5O` → `$50`, `1O days` → `10 days`, `2O17` → `2017`); inside words 0→O/o and 1→l/I (`PT0` → `PTO`, `emp1oyees` → `employees`). 2 and 3 are never touched, so `R2`/`R3` survive. "Effective: Jan 1 2O17" becomes `effective_date: 2017-01-01` | 34 OCR-damaged tokens in 4 files (Task 1 issue #3). After the repair, "PTO" and "$50" are searchable, and the date that marks the scans as obsolete is a field |

## Metadata on every chunk

`_metadata.csv`: `path`, `title`, `owner_team`, `acl_groups`, `last_modified`, `source_system`.
Parsed: `doc_id`, `version`, `status`, `effective_date`, `supersedes`, `content_date`, `marking`,
`mirrors`, `proposed_effective_date`, `owner`, `edited_by`. Per chunk: `section`, `chunk`, `language`,
`format`. When a duplicate is found: `duplicate_of`, `duplicate_kind`.

**`last_modified` is copied but never used as a version date** (the brief's trap). Per source system:
- `policy-portal`: it equals the in-document effective date. That's fine, but the parsed `effective_date` is used anyway.
- `intranet-legacy`: **2026-01-15 for all four pages, the migration date.** That makes the 2024 handbook
  look newer than PTO v2, sick leave and parental leave v2.
- `scanned-archive`: 2023-08-09, the scan date (the content is from 2016–2019).
- `wiki`: the page's last edit, which isn't the content date either (Demo Rover Booking was "edited
  2026-04-15" but says "retired in July 2026").
- `drive` (meetings): the meeting date. `intranet` (newsletters): the issue date.

So Task 5 has `effective_date` (19 policies + the 2017 scan), `content_date` and `status` to work
with, and `last_modified` only as the export recorded it.

## Deduplication

Three kinds, three policies (measured on the whole corpus, numbers in `RESULTS.md`):

1. **Repeated sentences within a document** (the manual): **removed** at parse time, first occurrence
   kept. 1,064 sentences.
2. **Exact duplicate chunks across documents** (sha1 of the normalised chunk body): keep the most
   authoritative, label the rest. **0 found** in this corpus, but checked on every ingest.
3. **Near-duplicate documents across source systems**: the share of the smaller document's word
   3-shingles found in the other (containment) is ≥ 0.75, or the document declares it ("This page
   mirrors IT-STD-003 v2.0"). **Kept and labelled:** every chunk of the copy gets `duplicate_of` = the
   document from the more authoritative source (policy-portal > drive > wiki > intranet >
   intranet-legacy > scanned-archive; a draft never outranks an approved text). **1 found:**
   `wiki/it/Password_Policy.html` → `IT-STD-003`, containment 0.759, also declared.

**Why label, not delete.**
- A copy is a ranking question: it usually agrees with the original, and when it doesn't it's a
  stale version, which is Task 5's job.
- Deleting it at ingest would make one document's index content depend on another's, so editing
  IT-STD-003 would have to re-ingest the wiki page. That breaks the per-document incremental contract.
- Labelling runs over the stored chunk texts after every ingest, with no embedding call (0.02 s).

**Deliberately not duplicates:** documents from the *same* source that share a template. Team wiki
pages reach containment up to 0.79, monthly newsletters 0.80, meeting notes 0.74. They share filler
("Retro every two weeks", "Reminder: the robotics lab is closed…"), not facts. Merging them would
delete real, different information ("Karim is on PTO next week" vs "Sofia is on PTO next week").

**Not handled here: versions.** The legacy handbook and PTO v2/v3 overlap 0.5–0.7 at document level,
but they're versions that disagree, not copies. Choosing the current one is Task 5.

## Incremental indexing

- **Per-document content hash.** The manifest stores each document's sha256 and chunk ids.
- **On re-ingest:** only new or changed documents are parsed and embedded. Removed ones lose their
  vectors, and unchanged ones are reused untouched.
- **Index signature.** The loader version (`LOADER_VERSION`) is part of it, so changing a loader
  rebuilds the index instead of mixing old and new chunks.
- **Answer cache.** `corpus_version`, a hash of every document's hash, changes on any add, change or
  remove, and the Week 2 answer cache keys on it. Every cached answer is invalidated, not only the ones
  that cited the changed document: a new or changed document can change the answer to *any* question
  (it may now outrank what was retrieved before), so per-document invalidation would serve stale answers.
- **Skipped documents.** A document that can't be parsed is skipped **with its reason**: in the stats,
  in a warning, in `ingestion_report.json` next to the index, and as a JSON log line
  (`"event": "ingest_document_skipped"`). Nothing is skipped silently. On this corpus: 0 skipped.
