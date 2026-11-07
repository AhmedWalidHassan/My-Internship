# Capstone Evaluation Results

## Latest experiment
- **Date:** 2026-11-07
- **LangSmith experiment name/link:** northwind-hybrid-37cb6c4b
- **Dataset size:** 30 examples (5 out-of-scope)
- **Retriever used:** hybrid
- **Model:** qwen3.5:4b (judge: qwen3.5:4b)

## Scores
| Metric | Score |
|--------|-------|
| Correctness | 1.00 |
| Groundedness / faithfulness | 1.00 |
| Retrieval hit-rate | 1.00 (answerable questions only) |

## Failure analysis
- **Biggest failure mode observed:** In experiment 1, over-strict refusal of an answerable question
  that needs a small inference ("Can I take PTO during my first month?" was refused although the correct
  draft, "No, PTO can't be used in the first 90 days", was generated twice). One failure remains in
  experiment 2: for "which Fleet Manager version?" the answer says the version is not in the documents,
  although it is (Fleet Manager 4.2). The LLM judge marked it correct in both runs, so true correctness
  is 29/30 (0.97), not 1.00.
- **Root cause (retrieval vs. generation vs. prompt):** PTO case: prompt. Retrieval and grading were
  fine; the hallucination checker required claims to be literally stated and rejected a correct draft, and
  the retry reproduced the same answer (temperature 0). Fleet Manager case: retrieval. Only the
  "Key Specifications" passage was graded relevant, so the "Software" section holding the version was never
  used. The eval is also weak: the judge is the same 4B model (lenient), and hit-rate only checks the file,
  not the section.
- **What I would change next to fix it:** Retrieve more passages or per sub-question for multi-part
  questions; use a stronger judge via --judge-model; add expected sections to the dataset so hit-rate is
  per section; make the retry change something (prompt or context) instead of repeating the same call.

| 2 | looser grounding check | 1.00 | 1.00 | hit-rate 1.00; PTO fixed. Manual review: judge missed the Fleet Manager version error, true correctness 0.97 |
