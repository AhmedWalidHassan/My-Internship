 # Task 3 — Embeddings & Vector Stores

## Retrieval Observation

- **Query:** How much PTO do I get?
- **Expected result:** The employee handbook states that full-time employees accrue 1.67 days of PTO per month (20 days per year).
- **Retrieved result:** The first retrieved chunk from `employee_handbook.md` correctly contained the PTO policy. However, the second and third chunks from `hr_policies.md` discussed performance reviews and expense reimbursement instead of directly answering the question.
- **Possible reason:** The vector search returned the three nearest chunks, but not all of them were directly relevant to the query. The exact reason for their ranking cannot be determined from the output alone.
- **Possible improvement:** Inspect the retrieved chunks and compare retrieval results using different queries and chunking settings. Consider evaluating similarity scores to better understand retrieval quality.
