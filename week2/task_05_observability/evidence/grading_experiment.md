# Stretch experiment: grade 2 passages per search instead of 6 (MAX_DOCS_TO_GRADE)
# 2026-11-16, local Ollama qwen3.5:4b (also the judge), hybrid retriever k=4, 28 eval examples.
# Correctness/groundedness: `MAX_DOCS_TO_GRADE=<n> python week1/capstone_internal_docs_assistant/app.py eval`
# Cost/latency: `MAX_DOCS_TO_GRADE=<n> make cost` (cost_report.md / cost_report_grade2.md). Only the setting changed.

## MAX_DOCS_TO_GRADE=6
- **LangSmith experiment:** [capstone-82f17940](https://smith.langchain.com/o/d25a7522-0a1b-46db-9753-429d87a65bfc/datasets/24ab974a-10a4-4542-ae66-c91e12f6390c/compare?selectedSessions=f77540f8-140a-43cf-809d-d348d64a893b) (dataset `northwind-capstone-eval`)
| Metric | Score |
|--------|-------|
| Correctness | 0.96 |
| Groundedness / faithfulness | 0.96 |
| Retrieval hit-rate | 1.00 |

Failing examples:
- How do I get on the VPN from home? → **groundedness** = 0 (judge: NO)
- Do I need approval for a Figma license? → **correctness** = 0 (refused an answerable question | rejected answer: You need approval for a Figma license if its cost is above $50/month. Licenses under $50/month are auto-approved. | fact-check said: The first sentence claims Figma specifically requires approval above $50/month, but the context only states this rule applies generally to licenses and does not mention Figma by name.

## MAX_DOCS_TO_GRADE=2
- **LangSmith experiment:** [capstone-ed3f9c4b](https://smith.langchain.com/o/d25a7522-0a1b-46db-9753-429d87a65bfc/datasets/24ab974a-10a4-4542-ae66-c91e12f6390c/compare?selectedSessions=aaea5455-92ed-42f6-8d68-b7020a758021) (dataset `northwind-capstone-eval`)
| Metric | Score |
|--------|-------|
| Correctness | 0.82 |
| Groundedness / faithfulness | 0.96 |
| Retrieval hit-rate | 1.00 |

Failing examples:
- How much weight can the Warehouse Rover R2 carry? → **correctness** = 0 (refused an answerable question | rejected answer: I don't know based on the provided documents. | fact-check said: The context does not contain any information to support the statement "I don't know based on the provided documents."
- How do I get on the VPN from home? → **groundedness** = 0 (judge: NO)
- What is the daily meal limit when travelling abroad? → **correctness** = 0 (refused an answerable question | rejected answer: I don't know based on the provided documents. Sources: | fact-check said: The answer states "I don't know," which contradicts the clear information present in both documents regarding travel and PTO policies.
- Can the R2 be used outdoors? → **correctness** = 0 (refused an answerable question | rejected answer: No, the R2 cannot be used outdoors because it is not rated for outdoor or wet environments (IP54 only). | fact-check said: The first sentence claims the R2 cannot be used outdoors because it lacks outdoor/wet ratings (IP54 only), which is directly supported by the context stating "Not rated for outdoor or wet environments (IP54 only)."
- Do I need approval for a Figma license? → **correctness** = 0 (refused an answerable question | rejected answer: You need approval for a Figma license if its cost is above $50/month. Licenses under $50/month are auto-approved. | fact-check said: The first sentence claims Figma specifically requires approval above $50/month, but the context only states this rule applies generally to licenses and does not mention Figma by name.
- time off carry rules? → **correctness** = 0 (judge: INCORRECT)

