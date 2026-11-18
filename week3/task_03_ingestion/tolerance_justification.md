Tolerance 0.08 for correctness and groundedness, unchanged from Week 2 and Week 3 Task 2 (justification: week3/task_02_eval_at_scale/tolerance_justification_v3.md). This baseline is re-set in Week 3 Task 3 because the system changed a lot (every format is now parsed: deterministic 0.314 -> 0.743, correctness 0.357 -> 0.500 on the same dev split). Leaving the Task 2 baseline in place would let a regression of up to 0.22 correctness through unseen.

Measured 2026-11-18, dataset northwind-eval-v3 (dev, 70), qwen3.5:4b generator, gemma3:4b judge, laptop GPU: two full dev runs after the ingestion change were identical, answer for answer and verdict for verdict (spread 0.000).

Known weakness: the gemma3:4b correctness judge (with the stricter Task 2 prompt) is now too strict on CORRECT answers: on 18 dev examples the deterministic check passes and the judge says incorrect, and about 13 of those are plainly correct (it penalises reference details the question did not ask for). Correctness (0.500) therefore understates the system; the deterministic score (0.743) is the more honest floor here. Recalibrating the judge (new human labels on this system's answers) is a follow-up, not part of the ingestion change.

Cost: +20% mean cost per question fails the gate (kept). This run: $0.000698 per question, +1.7% vs the Task 2 baseline.
