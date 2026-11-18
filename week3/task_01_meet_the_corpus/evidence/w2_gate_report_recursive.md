## Eval gate: ✅ passed

| Metric | Baseline | This run | Δ | Tolerance |
|---|---:|---:|---:|---:|
| correctness | 0.92 | 0.84 | -0.08 | 0.08 |
| groundedness | 0.97 | 0.95 | -0.03 | 0.08 |
| retrieval_hit | 1.00 | 0.95 | -0.05 | not gated |
| mean cost / question | $0.000467 | $0.000542 | +16% | +20% |

**By category** (correctness / groundedness):

| Category | n | Baseline | This run |
|---|---:|---:|---:|
| factual | 19 | 0.95 / 1.00 | 0.74 / 0.95 |
| multi-hop | 2 | 0.50 / 1.00 | 1.00 / 1.00 |
| multi-part | 7 | 1.00 / 0.86 | 0.86 / 0.86 |
| refusal | 6 | 1.00 / 1.00 | 1.00 / 1.00 |
| follow-up | 2 | 0.50 / 1.00 | 1.00 / 1.00 |
| keyword | 2 | 1.00 / 1.00 | 1.00 / 1.00 |

**Examples that changed verdict vs the baseline:** 6 regressed, 2 improved

<details open><summary>Regressed (6)</summary>

| # | Category | Metric | Question | Judge / reason |
|---:|---|---|---|---|
| 2 | factual | correctness 1 → 0 | time off carry rules? | judge: INCORRECT |
| 3 | factual | correctness 1 → 0 | Can I take time off in my first months? | judge: INCORRECT |
| 10 | factual | correctness 1 → 0 | What is the daily meal limit when travelling abroad? | refused an answerable question / rejected answer: The daily meal limit for travel abroad is $80 according to the 2019 policy, or $110 according to the HR policies document. / fact- |
| 12 | factual | correctness 1 → 0 | How long do I have to file an expense report? | refused an answerable question / rejected answer: Based on the provided documents, there are conflicting deadlines for filing expense reports. The 2019 Expense Policy states claims |
| 24 | factual | groundedness 1 → 0 | Can the R2 be used outdoors? | judge: NO |
| 31 | multi-part | correctness 1 → 0 | What are the known limitations of the Warehouse Rover R2? | judge: INCORRECT |

</details>

<details><summary>Improved (2)</summary>

| # | Category | Metric | Question | Judge / reason |
|---:|---|---|---|---|
| 29 | multi-hop | correctness 0 → 1 | I just referred a friend who got hired. When do I get my referral bonus, and when will my friend be allowed to use their PTO? | judge: CORRECT |
| 35 | follow-up | correctness 0 → 1 | Do they carry over? | judge: CORRECT |

</details>

<sub>Run: 38 examples, model `ollama:qwen3.5:4b`, judge `ollama:qwen3.5:4b (same model as the generator)`, Linux x86_64 py3.14.10, 313.0 s, commit `9ca3dcc0`. Baseline: 2026-11-18, dataset 58fefe13fc23.</sub>
