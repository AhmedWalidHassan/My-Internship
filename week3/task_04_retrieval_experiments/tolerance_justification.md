Generation (correctness, groundedness): tolerance 0.08, unchanged since Week 2 and re-justified in Week 3 Task 2 and Task 3 (week3/task_02_eval_at_scale/tolerance_justification_v3.md, week3/task_03_ingestion/tolerance_justification.md). The generation baseline is still the Task 3 system: Task 4 shipped no retrieval change.

Retrieval (Week 3 Task 4): recall@5 tolerance 0.017, MRR tolerance 0.02, on the 60 answerable dev questions.

Derived from the noise floor (week3/EXPERIMENTS.md): three baseline runs, plus a fastembed/ONNX rebuild (the CI backend) and a CPU PyTorch rebuild (the container's), gave identical document rankings for all 60 questions. The noise is 0.000, so the smallest real change is one question: 1/60 = 0.017 recall@5, and 0.008 MRR for one question moving from rank 1 to rank 2.
- recall@5: one question may leave the top 5 without failing the gate. It still shows up by name in the report, to absorb a library or model-version change that flips a tie, which the noise runs could not exercise. Two questions (0.033) fail. EXP-03 (dropping the context header) was −0.033 and would have been caught.
- MRR: 0.02 is about two or three questions slipping one rank. EXP-03 was −0.031 and EXP-05 −0.055; both would fail.

Where it runs: in a new key-free per-PR job (retrieval-gate: local ONNX embeddings, no LLM, no secrets) and in the eval-gate job, so a retrieval regression is caught before merge, not the next night.
