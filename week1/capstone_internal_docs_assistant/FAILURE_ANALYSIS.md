## Failure analysis

Latest experiment `capstone-91743e16` (28 examples: 24 answerable, 4 out of scope):
correctness **0.96**, groundedness **0.96**, retrieval hit-rate **1.00**, no run errors.
Both scores below 1.00 come from a single example each, so one example is worth 3.6 points
and I read them as signals to investigate, not precise measurements.

- **Biggest failure mode observed:** the small local model that acts as the *judge* is
  unreliable in both directions. It wrongly rejected a correct, supported answer (Figma),
  disagreed with itself on another (VPN), and accepted an answer containing an invented
  claim (first months). Retrieval and generation were not the bottleneck.

- **Root cause (retrieval vs. generation vs. prompt):** the verification stage (a 4B model
  used as the relevance grader, the in-graph fact-check and the eval judge), not retrieval
  and not generation. `retrieval_hit` was 1.00 in the last two runs, and the key fact was
  in the kept passages in every failing example.

- **What I would change next to fix it:** see the prioritized list at the end.

### The three examples that matter

**1. Figma license: the only correctness failure (an over-refusal).**
The passage kept for this question contains both "Figma" and the rule "Licenses under
$50/month are auto-approved; above that requires manager sign-off". The model generated a
correct answer ("You need approval for a Figma license if its cost is above $50/month.
Licenses under $50/month are auto-approved."). The fact-check rejected it three times,
saying the context "does not mention Figma by name", which is false: Figma is named in the
question line of that same passage. Each rejection triggered a query rewrite, so the run took
17 steps and ended in "I don't know". Retrieval ✓, generation ✓, fact-check ✗. Rewriting the
query cannot fix a judge error, so the loop only wasted time.

**2. VPN: groundedness 0 is a false alarm.**
The answer (install GlobalConnect, sign in with SSO, approve the MFA push, the VPN is
required from outside the office network) is fully supported by the retrieved passage.
The in-graph fact-check accepted it (no rewrite happened), but the eval judge, using the same
prompt and the same context, said NO. That is the judge disagreeing with itself. The eval
comment only says "judge: NO" without reasoning, so I can't be sure why. My guess is that it
objected to "from home" versus "outside the office network", but that is unverified.

**3. First months: a real unsupported claim that both checks missed.**
The answer says "...there is no restriction preventing its use in your first months" about
sick leave. The handbook says only that employees get 10 paid sick days per year, separate
from PTO. It says nothing about restrictions or waiting periods. This answer passed the
fact-check (on the second attempt) and scored groundedness 1. So on these two examples the
groundedness metric is inverted: it flagged a correct answer and passed an invented one.
**The groundedness score of 0.96 therefore understates the real problem: at least 1 of 28
answers (3.6%) contains an unsupported claim.**

Minor: a few answers add true but unrequested detail (the "time off carry rules?" answer
also states that sick days do not carry over; the referral answer adds "no limit on the
number of referrals"). This is a side effect of the more lenient relevance grader and is
not penalized by any metric.

### How the failure mode moved across experiments

| # | Change made | Correctness | Groundedness | Retrieval | What failed |
|---|-------------|-------------|--------------|-----------|-------------|
| 1 | baseline | 0.75 | 1.00 | 0.89 | 3 questions wrongly sent to "direct" or graded out, plus 4 false failures caused by my own over-specified reference answers |
| 2 | router biased toward searching, inline "Sources:" stripping fixed, references and judge prompt corrected, stricter grounding prompt | 0.79 | 1.00 | 1.00 | 6 over-refusals: 3 where the relevance grader rejected every passage, 3 where the fact-check rejected a correct answer |
| 3 | last-resort fallback (top 3 passages if the grader rejects all), more lenient relevance prompt, softer grounding prompt | **0.96** | **0.96** | 1.00 | 1 over-refusal (Figma), 1 judge false alarm (VPN), 1 missed hallucination (first months) |

Experiments 1 and 2 are **not directly comparable**: I changed the evaluation (references,
judge prompt) at the same time as the system. Experiments 2 and 3 only differ in the system.
Each experiment was a single run, and the VPN disagreement shows that run-to-run noise is real.

What the evidence supports:
- **Router fix worked.** No answerable question was sent to "direct" in runs 2 and 3.
- **Fallback worked.** For the alcohol, outdoors and personal-phone questions the relevance
  grader rejected every passage twice; the fallback passed the top 3 passages and all three
  were then answered correctly (they were refused in run 2).
- **Softer grounding prompt fixed two over-refusals** (adoptive parent and first months were
  refused in run 2) but did not fix Figma, and the first-months answer that now gets through
  contains an invented claim. This is a precision/recall trade-off in a small judge, not a
  clean win.
- Out-of-scope questions were handled correctly in all four cases: France and football were
  refused without searching, and the CEO's address and dental insurance went through the full
  retry loop and were refused (the latter took 19 s).

### What I would change next (in priority order)

1. **Use a stronger judge.** A larger model (even a hosted one used only for grading) for the
   fact-check and the eval would address the main root cause. At minimum, set temperature to
   0 and take a majority of 3 verdicts, since the same input produced different verdicts.
2. **Make unsupported claims structurally detectable.** Ask the generator to quote the exact
   sentence that supports each claim, then verify in code that each quote is a substring of
   the retrieved text. This catches the "no restriction preventing its use" kind of invention
   without relying on the judge. A numbers-only check would not have caught that example.
3. **Don't rewrite the query when retrieval was fine.** If the passages were kept but the
   answer failed the check, regenerate once instead of searching again. The Figma run spent
   17 steps rewriting a query that was already good.
4. **Make the evaluation able to fail.** Add adversarial examples designed to tempt
   hallucination (such as the sick-leave waiting-period question), log the judge's reasoning in
   every eval comment, and report groundedness separately for non-refusal answers, since
   refusals count as trivially grounded.
5. **Tighten the relevance grader** or cap the number of kept passages, so answers stop
   including true but unrelated detail.

## Experiment log

| # | Change made | Correctness | Groundedness | Notes |
|---|-------------|-------------|--------------|-------|
| 1 | baseline (`capstone-ffca2dcf`) | 0.75 | 1.00 | router false negatives; 4 false failures from over-specified references |
| 2 | router bias, inline sources fix, fairer references/judge, strict grounding (`capstone-3c9b18b0`) | 0.79 | 1.00 | 6 over-refusals; metric changed, so not comparable to #1 |
| 3 | grader fallback, lenient grader, softer grounding (`capstone-91743e16`) | 0.96 | 0.96 | 1 over-refusal, 1 judge false alarm, 1 missed hallucination |
