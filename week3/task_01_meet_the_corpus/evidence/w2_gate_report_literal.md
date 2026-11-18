## Eval gate: ❌ FAILED

**Why it failed:**
- **correctness** 0.158 is below the baseline 0.921 minus the tolerance 0.080 (floor 0.841)
- **mean cost per question** $0.000774 is more than 20% above the baseline $0.000467

| Metric | Baseline | This run | Δ | Tolerance |
|---|---:|---:|---:|---:|
| correctness | 0.92 | 0.16 | -0.76 | 0.08 |
| groundedness | 0.97 | 1.00 | +0.03 | 0.08 |
| retrieval_hit | 1.00 | 0.16 | -0.84 | not gated |
| mean cost / question | $0.000467 | $0.000774 | +66% | +20% |

**By category** (correctness / groundedness):

| Category | n | Baseline | This run |
|---|---:|---:|---:|
| factual | 19 | 0.95 / 1.00 | 0.00 / 1.00 |
| multi-hop | 2 | 0.50 / 1.00 | 0.00 / 1.00 |
| multi-part | 7 | 1.00 / 0.86 | 0.00 / 1.00 |
| refusal | 6 | 1.00 / 1.00 | 1.00 / 1.00 |
| follow-up | 2 | 0.50 / 1.00 | 0.00 / 1.00 |
| keyword | 2 | 1.00 / 1.00 | 0.00 / 1.00 |

**Examples that changed verdict vs the baseline:** 29 regressed, 1 improved

<details open><summary>Regressed (29)</summary>

| # | Category | Metric | Question | Judge / reason |
|---:|---|---|---|---|
| 1 | factual | correctness 1 → 0 | How many vacation days do I get a year? | refused an answerable question / rejected answer: I don't know based on the provided documents. / fact-check said: The answer states "I don't know based on the provided documents," |
| 2 | factual | correctness 1 → 0 | time off carry rules? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 3 | factual | correctness 1 → 0 | Can I take time off in my first months? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 4 | factual | correctness 1 → 0 | How far ahead do I have to ask for PTO? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 5 | factual | correctness 1 → 0 | How many sick days are there per year? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 6 | factual | correctness 1 → 0 | When do I need a doctor's note? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 7 | factual | correctness 1 → 0 | How many days a week can I work from home? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: README.md, _metadata.csv, _directory.csv / fact-check said: The context doe |
| 8 | factual | correctness 1 → 0 | What is the home-office stipend? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The statement "I don't know based on the provided docume |
| 9 | factual | correctness 1 → 0 | How long is paid leave for an adoptive parent? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 10 | factual | correctness 1 → 0 | What is the daily meal limit when travelling abroad? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The statement "I don't know based on the provided docume |
| 11 | factual | correctness 1 → 0 | Is alcohol reimbursable? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know," which contradicts the  |
| 12 | factual | correctness 1 → 0 | How long do I have to file an expense report? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 13 | multi-part | correctness 1 → 0 | How much is the referral bonus and when is it paid? | refused an answerable question / rejected answer: I don't know based on the provided documents. / fact-check said: The answer states "I don't know based on the provided documents," |
| 14 | factual | correctness 1 → 0 | How often are performance reviews held? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The context does not contain any information regarding t |
| 15 | factual | correctness 1 → 0 | What is my annual learning budget? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know," which is not supported |
| 16 | multi-part | correctness 1 → 0 | My laptop got stolen, what do I do? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 17 | multi-part | correctness 1 → 0 | What are the password rules? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer claims ignorance and cites sources, which con |
| 18 | multi-part | correctness 1 → 0 | How do I get on the VPN from home? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 19 | factual | correctness 1 → 0 | Can I open our source code on my personal phone? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer claims ignorance and cites sources, which con |
| 21 | factual | correctness 1 → 0 | How much weight can the Warehouse Rover R2 carry? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 22 | factual | correctness 1 → 0 | How fast does the rover go with a load? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 23 | multi-part | correctness 1 → 0 | What does premium support include? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer claims ignorance and cites sources, which con |
| 24 | factual | correctness 1 → 0 | Can the R2 be used outdoors? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 30 | multi-hop | correctness 1 → 0 | I want to work fully remote. What do I need to get approved, and how do I reach internal systems from home? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer claims ignorance and cites sources, which con |
| 31 | multi-part | correctness 1 → 0 | What are the known limitations of the Warehouse Rover R2? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 32 | multi-part | correctness 1 → 0 | What are the rules for booking business travel? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 36 | follow-up | correctness 1 → 0 | And what does the standard plan cover? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 37 | keyword | correctness 1 → 0 | What does Fleet Manager 4.2 handle? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |
| 38 | keyword | correctness 1 → 0 | Does the R2 support 5G? | refused an answerable question / rejected answer: I don't know based on the provided documents. Sources: / fact-check said: The answer states "I don't know based on the provided do |

</details>

<details><summary>Improved (1)</summary>

| # | Category | Metric | Question | Judge / reason |
|---:|---|---|---|---|
| 18 | multi-part | groundedness 0 → 1 | How do I get on the VPN from home? | refusal: no claims to support |

</details>

<sub>Run: 38 examples, model `ollama:qwen3.5:4b`, judge `ollama:qwen3.5:4b (same model as the generator)`, Linux x86_64 py3.14.10, 150.7 s, commit `9ca3dcc0`. Baseline: 2026-11-18, dataset 58fefe13fc23.</sub>
