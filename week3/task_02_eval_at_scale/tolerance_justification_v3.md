Tolerance 0.08 for correctness and groundedness, kept from Week 2 (the brief: keep it unless Task 4's noise floor says otherwise). On the 70-example dev split that is 5.6 examples: the gate fires on a drop of 6 or more (>= 0.086).

Measured 2026-11-18, dataset northwind-eval-v3 (dev, 70), generator qwen3.5:4b, judge gemma3:4b (a different model, as Week 3 requires), laptop GPU:

1. Same hardware, repeated: dev runs 2 and 3 were identical, answer for answer and verdict for verdict (spread 0.000 on every metric).
2. The judge alone, replayed on the same 70 answers: at most 1 verdict of 70 moved (0.014) between replays, so the judge is close to, but not exactly, deterministic.
3. Week 2's hardware-change evidence still applies (GPU vs CPU/ONNX moved 3 verdicts of 38: ~0.08), and CI builds its index with fastembed (ONNX) rather than PyTorch.
4. Real regressions on this set are large: the Week 2 loader as shipped (README only) scores 0.15 deterministic on the seed set; losing the 118 readable documents would drop correctness by far more than 0.08.

Why not tighter: 0.03 (2 examples) is within the judge replay noise plus a hardware change. Why not looser: 0.10+ would let 7 examples (10% of dev) regress unseen.

Known weakness of what is gated: groundedness is 1.000 on every run because 32/70 answers are refusals (trivially grounded) and the gemma3:4b judge said YES to all 38 non-refusals; on six probes it caught only 1 of 3 planted unsupported claims. A groundedness drop is therefore unlikely to be seen until the judge is stronger. Correctness and the deterministic score carry the gate.

Cost: +20% mean cost per question fails the gate (kept from Week 2).
