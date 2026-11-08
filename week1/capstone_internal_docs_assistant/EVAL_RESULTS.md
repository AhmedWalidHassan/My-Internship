# Capstone Evaluation Results

<!-- AUTO:START -->
## Latest experiment
- **Date:** 2026-11-08
- **LangSmith experiment name/link:** capstone-91743e16 (dataset `northwind-capstone-eval`, smith.langchain.com → Datasets & Experiments)
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
- **Biggest failure mode observed:** (write this yourself from the list above and the LangSmith traces)
- **Root cause (retrieval vs. generation vs. prompt):**
- **What I would change next to fix it:**

## Experiment log (optional but encouraged)
| # | Change made | Correctness | Groundedness | Notes |
|---|-------------|-------------|--------------|-------|
| 1 | baseline | 0.75 | 1.00 | |
