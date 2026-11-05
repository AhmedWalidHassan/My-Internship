## Task 7: LangSmith tracing & evaluation

### Setup

- Dataset `rag-internship-eval` was created from `eval_dataset.jsonl`: 10
  examples, with `question` as input and the reference `answer` and `source`
  file as outputs.
- The system under test is the Task 4 RAG chain, loaded by file path (both
  tasks have a file called `starter.py`, so a normal import would import the
  wrong one). The target returns the answer, the retrieved context and the
  list of source files.

### Evaluators

1. **correctness** (LLM-as-judge): compares the answer to the reference answer.
2. **groundedness** (LLM-as-judge): is every claim in the answer supported by
   the retrieved context? This catches hallucination, and it is separate from
   correctness: an answer can be right but ungrounded, or wrong but grounded.
3. **retrieval_hit** (no LLM): was the gold source file among the retrieved
   chunks? It exists to separate bad retrieval from bad generation.

The judge is the same local 4B model that writes the answers, so it is a weak
and possibly lenient judge. See the limits below.

### Results: three experiments

| Experiment | correctness | groundedness | retrieval_hit | avg latency | avg tokens | empty answers |
|---|---:|---:|---:|---:|---:|---:|
| 1. original prompt, thinking on | 0.80 | 1.00 | 1.00 | 17 s | ~1,290 | 0 |
| 2. new prompt, thinking on | 0.60 | 0.50 | 1.00 | 67 s | ~3,330 | 4 |
| 3. new prompt, thinking off | 1.00 | 1.00 | 1.00 | 13 s | ~790 | 0 |

The new prompt asks for complete answers: include every relevant number,
limit, deadline and condition, and end with a sources line. Experiments 1 to 2
changed only the prompt. Experiments 2 to 3 changed only the thinking setting
(`reasoning=False`).

### What the traces and results told me about why

**Example that failed in experiment 1: the password question.** The answer gave
the length (14 characters) and rotation (180 days) but left out the lockout
(30 minutes after 5 failed attempts). The retrieved context in the exported
results contained the lockout sentence, so retrieval worked and the model
dropped the detail. This is **bad generation, not bad retrieval**, and it is
why `retrieval_hit` was 1.00 even for the failures. The parental-leave answer
had the same pattern (it left out "within 12 months of the birth or
placement"), and the new prompt fixed both.

**Experiment 2: the new prompt made things worse for a different reason.**
4 of 10 answers came back empty, each using exactly 4,096 tokens and taking
60 to 97 seconds. 4,096 matches the default context window, which holds the
prompt and the generated tokens together. My interpretation is that the
model (a "thinking" model) spent the whole budget on hidden reasoning, because
the exhaustive instruction gave it more to deliberate over, and was cut off
before writing any visible answer. The 6 runs that did finish were all
correct, and the aggregate scores hid this: the lower numbers came from empty
outputs, not from wrong answers.

**Experiment 3.** Turning thinking off removed the empty answers, brought the
average latency down to 13 s, and cut tokens from ~1,290 (experiment 1) to ~790,
which suggests that around 500 tokens per question in the original runs were
hidden reasoning. All three scores are 1.00.

### Problems I found by reading the answers

- **A hallucinated source.** In experiment 3, the parental-leave answer lists
  `Sources: employee_handbook.md, file1.md`. `file1.md` does not exist. The
  model copied the placeholder from my prompt's example line
  (`"Sources: file1.md, file2.md"`). The groundedness judge didn't catch it
  because I told it to ignore the source list. Fix: describe the format
  without literal file names, e.g. `End with one line: "Sources:" followed by
  the file names from the context that you used.` and rerun.
- **Judge failures scored as 0.** My first evaluator scored an empty or
  unparseable judge reply as 0, so a judge glitch counted as a wrong answer
  (in experiment 2 this dragged groundedness down on an answer that was
  actually fine). Better: retry once, then raise an evaluator error, and handle
  empty answers explicitly.

### Limits of these scores: 1.00 doesn't mean "done"

- **10 examples:** each one is worth 10 points, and one run can't separate real
  differences from noise. Rerun with `num_repetitions=3` before trusting a gap.
- **Lenient judge.** The SLA answer left out "24/7 coverage" and was still
  judged CORRECT, while the password answer in experiment 1 failed for a
  similar omission. A 4B model grading itself is inconsistent.
- **Saturated benchmark.** Everything scores 1.00, so it can't show further
  improvement or catch regressions. The dataset has no out-of-scope questions,
  so the refusal behavior isn't measured here.
- **`retrieval_hit` is file-level.** Each question retrieves 2 or 3 of the
  4 files, so a hit is nearly guaranteed. A chunk-level check (does the
  retrieved text contain the key fact?) would be stricter.
