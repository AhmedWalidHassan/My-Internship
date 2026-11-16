# Capstone Evaluation Results

<!-- AUTO:START -->
## Latest experiment
- **Date:** 2026-11-16
- **LangSmith experiment:** [capstone-47ff55d7](https://smith.langchain.com/o/d25a7522-0a1b-46db-9753-429d87a65bfc/datasets/24ab974a-10a4-4542-ae66-c91e12f6390c/compare?selectedSessions=c7c7d723-29c5-486d-af5f-a92c6f88ba35) (dataset `northwind-capstone-eval`)
- **Dataset size:** 28 examples (24 answerable + 4 out-of-scope)
- **Retriever used:** hybrid (BM25 + dense)
- **Model:** qwen3.5:4b

## Scores
| Metric | Score |
|--------|-------|
| Correctness | 0.96 |
| Groundedness / faithfulness | 0.96 |
| Retrieval hit-rate | 1.00 |

_Notes: refusals count as trivially grounded; the judge is the same small local model that writes the answers, so treat these numbers as a rough signal._

### Failing examples (auto-generated)
- How do I get on the VPN from home? → **groundedness** = 0 (judge: NO)
- Do I need approval for a Figma license? → **correctness** = 0 (refused an answerable question | rejected answer: You need approval for a Figma license if its cost is above $50/month. Licenses under $50/month are auto-approved. | fact-check said: The first sentence claims Figma specifically requires approval above $50/month, but the context only states this rule applies generally to licenses and does not mention Figma by name.
The second sentence accurately restates the context's information that licenses under $50/month are auto-approved.
ANSWER: NO)
<!-- AUTO:END -->

## Failure analysis

The full analysis (the three examples that matter, root cause, and the prioritized fix list) is in
[`FAILURE_ANALYSIS.md`](FAILURE_ANALYSIS.md). In short, the biggest failure mode is the
**verification stage**, not retrieval: the same 4B model is relevance grader, in-graph fact-check
and eval judge, and it is unreliable in both directions (it rejects supported answers and passes
an invented one).

## Experiment log

| # | Date | Experiment | Change made | Correctness | Groundedness | Retrieval hit |
|---|---|---|---|---:|---:|---:|
| 1 | 2026-11-08 | `capstone-ffca2dcf` | baseline | 0.75 | 1.00 | 0.89 |
| 2 | 2026-11-08 | `capstone-3c9b18b0` | router bias, inline-sources fix, fairer references and judge, strict grounding | 0.79 | 1.00 | 1.00 |
| 3 | 2026-11-08 | `capstone-91743e16` | grader fallback, lenient grader, softer grounding | 0.96 | 0.96 | 1.00 |
| 4 | 2026-11-16 | [`capstone-47ff55d7`](https://smith.langchain.com/o/d25a7522-0a1b-46db-9753-429d87a65bfc/datasets/24ab974a-10a4-4542-ae66-c91e12f6390c/compare?selectedSessions=c7c7d723-29c5-486d-af5f-a92c6f88ba35) | Week 2 Task 1 re-run (logging/config only, no behaviour change) | 0.96 | 0.96 | 1.00 |
