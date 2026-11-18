## Eval gate: ✅ passed

| Metric | Baseline | This run | Δ | Tolerance |
|---|---:|---:|---:|---:|
| correctness | 0.36 | 0.50 | +0.14 | 0.08 |
| groundedness | 1.00 | 0.99 | -0.01 | 0.08 |
| deterministic | 0.31 | 0.74 | +0.43 | not gated |
| mean cost / question | $0.000687 | $0.000698 | +2% | +20% |

**By category** (correctness / groundedness):

| Category | n | Baseline | This run |
|---|---:|---:|---:|
| factual | 10 | 0.70 / 1.00 | 0.70 / 0.90 |
| table | 4 | 0.00 / 1.00 | 0.75 / 1.00 |
| keyword | 4 | 0.50 / 1.00 | 0.75 / 1.00 |
| version | 5 | 0.00 / 1.00 | 0.40 / 1.00 |
| conflict | 3 | 0.00 / 1.00 | 0.33 / 1.00 |
| draft | 4 | 0.50 / 1.00 | 0.00 / 1.00 |
| multi_hop | 4 | 0.25 / 1.00 | 0.00 / 1.00 |
| multi_part | 4 | 0.25 / 1.00 | 1.00 / 1.00 |
| ambiguous | 3 | 0.67 / 1.00 | 1.00 / 1.00 |
| long_doc | 4 | 0.00 / 1.00 | 0.25 / 1.00 |
| cross_lingual | 4 | 0.00 / 1.00 | 0.00 / 1.00 |
| follow_up | 4 | 0.25 / 1.00 | 0.25 / 1.00 |
| personalized | 4 | 0.00 / 1.00 | 0.25 / 1.00 |
| access | 7 | 0.43 / 1.00 | 0.43 / 1.00 |
| out_of_scope | 6 | 1.00 / 1.00 | 1.00 / 1.00 |

**Examples that changed verdict vs the baseline:** 9 regressed, 18 improved

<details open><summary>Regressed (9)</summary>

| # | Category | Metric | Question | Judge / reason |
|---:|---|---|---|---|
| 4 | factual | correctness 1 → 0 | How far ahead do I have to ask for PTO? | judge: INCORRECT |
| s29 | factual | correctness 1 → 0 | How quickly do I have to report a lost laptop? | judge: INCORRECT |
| s29 | factual | groundedness 1 → 0 | How quickly do I have to report a lost laptop? | judge: NO |
| n08 | draft | correctness 1 → 0 | Is Northwind switching to flexible time off? | judge: INCORRECT |
| n09 | draft | correctness 1 → 0 | What is the minimum amount of time off I must take under the flexible time off policy? | judge: INCORRECT |
| 29 | multi_hop | correctness 1 → 0 | I just referred a friend who got hired. When do I get my referral bonus, and when will my friend be allowed to use their PTO? | refused an answerable question / rejected answer: You will receive your referral bonus in two equal instalments: 50% after the new hire completes 90 days and 50% after 12 months. Y |
| 36 | follow_up | correctness 1 → 0 | And what does the standard plan cover? | judge: INCORRECT |
| s18 | access | correctness 1 → 0 | What is the salary range for an L4 engineer in Austin? | answered an out-of-scope question |
| s22 | access | correctness 1 → 0 | How long is a performance improvement plan? | answered an out-of-scope question |

</details>

<details><summary>Improved (18)</summary>

| # | Category | Metric | Question | Judge / reason |
|---:|---|---|---|---|
| 20 | factual | correctness 0 → 1 | Do I need approval for a Figma license? | judge: CORRECT |
| 24 | factual | correctness 0 → 1 | Can the R2 be used outdoors? | judge: CORRECT |
| n01 | table | correctness 0 → 1 | What is the hotel cap per night for a business trip to India? | judge: CORRECT |
| n02 | table | correctness 0 → 1 | How much does the 5G connectivity module cost? | judge: CORRECT |
| s06 | table | correctness 0 → 1 | What is the hotel cap per night for a business trip to Germany? | judge: CORRECT |
| s34 | keyword | correctness 0 → 1 | What does error E-271 indicate? | judge: CORRECT |
| 3 | version | correctness 0 → 1 | Can I take time off in my first months? | judge: CORRECT |
| 8 | version | correctness 0 → 1 | What is the home-office stipend? | judge: CORRECT |
| 18 | conflict | correctness 0 → 1 | How do I get on the VPN from home? | judge: CORRECT |
| 16 | multi_part | correctness 0 → 1 | My laptop got stolen, what do I do? | judge: CORRECT |
| 17 | multi_part | correctness 0 → 1 | What are the password rules? | judge: CORRECT |
| 32 | multi_part | correctness 0 → 1 | What are the rules for booking business travel? | judge: CORRECT |
| n20 | ambiguous | correctness 0 → 1 | Which battery pack does the rover use? | judge: CORRECT |
| n14 | long_doc | correctness 0 → 1 | Can the R3 work on an outdoor loading dock in hot weather? | judge: CORRECT |
| s26 | follow_up | correctness 0 → 1 | And how many of them can I carry over? | judge: CORRECT |
| n24 | personalized | correctness 0 → 1 | How many PTO days do I get this year? | judge: CORRECT |
| n32 | access | correctness 0 → 1 | How long is a performance improvement plan? | judge: CORRECT |
| s19 | access | correctness 0 → 1 | What is the salary range for an L4 engineer in Austin? | judge: CORRECT |

</details>

<sub>Run: 70 examples, model `ollama:qwen3.5:4b`, judge `ollama:gemma3:4b`, Linux x86_64 py3.14.10, 638.6 s, commit `76f82e95`. Baseline: 2026-11-18, dataset 5d9544921fd6.</sub>
