# Who's asking: access control at every layer

The brief is in [README.md](README.md). The numbers are in
[`week3/RESULTS.md`](../RESULTS.md#task-6--whos-asking) and [`week3/COST.md`](../COST.md#task-6--access-control).
The code is in the service, as the Week 3 README requires:
- [`week1/common/access.py`](../../week1/common/access.py): the directory, the ACL check, the scope hash.
- [`week1/common/retrievers.py`](../../week1/common/retrievers.py): `for_scope`, the filtered searches.
- The graph's `retrieve` node and `Assistant.stream` in the capstone.
- [`app/main.py`](../../app/main.py), [`app/service.py`](../../app/service.py), [`app/cache.py`](../../app/cache.py),
  [`app/guardrails.py`](../../app/guardrails.py).
- Tests: [`tests/test_access.py`](../../tests/test_access.py).

## The one rule, and where each layer enforces it

**A user sees a chunk only if its `acl_groups` intersect the user's groups, and the groups come from
`_directory.csv`, looked up by `user_id`.** Never from the request body, the question, or the
conversation.

| Layer | What it does | Why there |
|---|---|---|
| **Identity** (`main.identify`) | `user_id` → groups, from the directory (re-read when the file changes). Missing or unknown: **401**. No default user | Everything after the lookup trusts these groups and nothing else |
| **BM25** (`retrievers._scoped`) | One BM25 index per access scope, built over the visible chunks only (cached per scope) | A restricted chunk is not in the index: it can't take a top-k slot, and it doesn't shape the term statistics (IDF) the ranking uses |
| **Dense** (`retrievers.ScopedDense`) | FAISS search with an ID selector over the visible vectors | The k nearest are the k nearest *visible* vectors |
| **No unscoped search** | The production retriever raises unless it is used through `for_scope(groups)` | A future code path can't forget the scope and silently search everything |
| **Graph `retrieve` node** | `can_see()` again on what the search returned, and again after Task 5's curation | Defence in depth. Curation can *add* passages (a superseded version's current one, a draft) from its catalog of every version |
| **Answer cache** | The key includes the scope hash | An HR answer is never served to an employee, and an employee's refusal never to HR. Same groups, same documents: shared entries are safe |
| **Sessions** | A session belongs to the user who started it. Anyone else: **403** on `/chat`, `/chat/stream`, `GET` and `DELETE /session` | Session memory holds earlier answers, and a follow-up's contextualize step reads them |
| **Log line** | `user_id`, `access_scope` (hash), `restricted_docs_used` | Who saw restricted content, from the logs alone (below) |
| **LangSmith** | A run whose scope reaches beyond the public one is **not traced** | The trace store is a third party, and a trace holds the passages and the answer |
| **Guardrails** | "I'm in HR", "my role is admin", "ignore the access rules": 400 | Early rejection and a metric. **Not** what protects the data (tested with it off) |
| **Rate limit** | Keyed by `user_id` (was `session_id`) | Otherwise new sessions get round the limit |

## Why filtering after retrieval, or after generation, isn't good enough

1. **`k`: restricted chunks take the slots.**
   - A retriever returns its top k. Filter afterwards and the user gets k minus the restricted ones,
     sometimes none. LangChain's own `FAISS(filter=…)` works that way: it fetches `fetch_k` = 20 and filters.
   - Measured on dev ([`postfilter_k.json`](evidence/postfilter_k.json)), each question asked as its own
     user, fused top 8: **9 of 70 questions would lose slots, 17 slots in total.**
   - n02 ("How much does the 5G connectivity module cost?", an employee) and s18 (salary bands, an
     employee) would keep only **4 of 8 passages**. Pre-filtering returns a full list from what they may see.
   - On this dev set no gold document fell out of the top 5. A bigger restricted corpus, or a question
     that matches HR documents better than the public answer, would push it out.
2. **After generation is too late: the model has read the restricted text.**
   - A post-check can't match a paraphrase ("about 140 thousand").
   - The contextualize and rewrite steps carry restricted words into the next query and into session
     memory.
   - The fact-check *passes* such an answer, because it is grounded: in the restricted passage.
   - The model provider and the trace store have already received it.
3. **Retrieval-time effects even when nothing is shown.**
   - A filtered-out chunk still changed the ranking (BM25 statistics, RRF positions).
   - A refusal that differs ("that's restricted") confirms the document exists. With the filter inside
     retrieval, the user gets the **same refusal** as for a question the corpus can't answer: the
     system has nothing to hide because it never saw anything.

Before this task the system leaked on dev ([`access_report_before.md`](evidence/access_report_before.md)):
- **13 of 70 questions** had a document their user may not see in the retrieved set, 9 of them outside
  the `access` category. "When do I need a doctor's note?" pulled in the salary bands, "How much is
  the referral bonus?" the 2026 compensation guidance, "Can the R2 be used outdoors?" the calibration
  guide.
- **4 of the 4** unauthorised `access` questions were answered with the restricted fact.

## Decisions

**A chunk with no ACL metadata is visible to no one.**
- "Visible to everyone" turns every metadata bug into a security incident: a missing column, a loader
  that drops a field, a new source system without ACLs. "Visible to no one" turns it into a missing
  answer.
- The missing answer is visible: a warning at every start, `documents_without_acl` in `/readyz`, and
  the eval's refusal count.
- This applies at ingestion too. The export loader used to default a missing `acl_groups` to `all`;
  it now keeps it empty.
- The Week 1 plain-folder corpus has no ACL source. Its chunks say `acl_groups: all` explicitly,
  rather than relying on the default.

**Changing a document's ACL re-indexes it.**
- The incremental ingest (Task 3) re-embedded a document only when its *file* changed. Tightening an
  ACL in `_metadata.csv` would have left the old ACL in the index, served for as long as the file
  stayed the same.
- A document's hash now includes its metadata row. The first start after this change re-indexes every
  document once (18 s on this laptop).

**The directory is required.**
- Missing, unreadable, empty, without a `groups` column, or with a `user_id` listed twice (which group
  set would be true?) means nobody can be identified. Every chat gets **503** `directory_unavailable`
  and `/readyz` is 503 with the reason.
- The file is re-read when it changes, so removing someone from `hr` applies to their next request.
- A bad edit fails closed rather than serving the old groups.

**What the log line records for an answer that used restricted documents:**
- `user_id`, `access_scope` (12 hex characters of `sha256` of the sorted group set) and
  `restricted_docs_used: true`.
- The chunk ids (`retrieved_ids`, `kept_ids`), which include restricted paths only for requests whose
  user was allowed to see them.
- **Never** the question text, the answer or the passages: that was true before, and it is pinned by
  `test_log_line_records_user_scope_hash_and_restricted_flag`.
- The hash lets a reviewer group requests by access level without the line listing who is in HR.
  Mapping a hash back to groups needs the directory, which the log reader may not have.
- The log store is internal and access-controlled. A path like `Project_Juniper_Workforce_Plan.md`
  appears there only next to a user who was allowed to read it.

**LangSmith traces: off for restricted scopes.**
- A trace contains the passages and the answer, and LangSmith is a third party.
- Requests from a user whose groups go beyond `all` run with tracing disabled (`traced: false`,
  `trace_url: null` in the log line). Their `/feedback` can't attach to a trace.
- Ordinary employees' requests are traced as before. They can only ever retrieve public chunks, so
  their traces hold nothing restricted.
- Implemented per graph step, never across a `yield`, because a streaming response resumes the
  generator in a different worker thread.

**Ambiguous rows the brief leaves open:**
- **A follow-up** runs retrieval again with the current user's scope; its history is that user's own
  conversation.
- **The prewarm** (Week 2 stretch) answers as the public scope only.
- **The CLI and the Streamlit-only mode** (no API) have no logged-in user and run as the public scope.

## Degradation table: new rows

| Failure | Behaviour | Tested by |
|---|---|---|
| Directory file missing or unreadable (also empty, no `groups` column, duplicate `user_id`) | **Fail closed:** every chat 503 `directory_unavailable` + `Retry-After`, `/readyz` 503 with the reason, no model call. Re-read on change, so fixing the file recovers without a restart | `tests/test_access.py::test_directory_missing_or_malformed_fails_closed` (4 cases) |
| Unknown `user_id` (or none) | **401** `unauthorized`, no default user, no model call; the stream refuses before it starts | `tests/test_access.py::test_unknown_or_missing_user_gets_401_never_a_default_user` |
| Chunk with no ACL metadata | **Visible to no one**: never retrieved, even for the user with every group. Counted in `/readyz` (`documents_without_acl`) and warned at startup | `tests/test_access.py::test_a_chunk_without_acl_metadata_is_visible_to_no_one` |

## What this does not solve

- **`user_id` is not authentication.** The brief makes it a stand-in for a verified SSO token, and the
  code treats it as one. But today anyone who can reach the API can send `"user_id": "u3002"`.
  The service must stay bound to localhost until a real identity provider fills that field (Week 2:
  "no auth yet").
- **Same-scope users share cached answers.** That's correct for access, and wrong once answers are
  personalised ("my PTO" depends on tenure). The stretch goal would need the user in the key.
- **The 4B model can still be talked into revealing what the asker *is* allowed to see**, phrased
  oddly. That is the Week 2 injection problem, not an access problem.
- **The guard rejects a real HR user** who writes "I work in People Operations, what is the merit
  budget?" That costs a rephrase, and the data was never at risk.

## Reproduce

```bash
make check                                                           # tests/test_access.py: leak matrix, cache, sessions, degradation
python week3/task_06_who_is_asking/scripts/access_report.py <eval run.json>   # leaks in a full eval run
python week3/task_06_who_is_asking/scripts/postfilter_k.py           # the `k` argument, measured
python week3/task_06_who_is_asking/scripts/live_attacks.py           # 3 attacks + the cache case, real model, guard on/off
python week2/task_06_caching/scripts/cache_benchmark.py workload --users directory   # hit rate with 6 users
```
