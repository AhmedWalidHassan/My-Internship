Tolerance 0.08 for correctness and groundedness = 3 of 38 examples. The gate fires on a drop of 4+ examples (>= 0.105). Measured 2026-11-16, qwen3.5:4b as generator and judge:

1. Same hardware, repeated (laptop GPU, temperature 0): two full runs were identical, verdict for verdict (spread 0.000). Run-to-run noise on the CI hardware is zero.
2. Hardware change (the same code on CPU with ONNX embeddings, i.e. GitHub-runner-like): 3 verdicts moved. Correctness went -2 examples (-0.053): the 4B fact-check rejected two correct answers and the system refused them. Groundedness went +1 (+0.026). A driver, Ollama or model update can do the same, so the gate must tolerate about 2 flips plus margin.
3. Real regressions, measured on the same hardware:
   - MAX_DOCS_TO_GRADE=1: -9 examples (correctness 0.921 -> 0.684). Caught with a wide margin.
   - Task 5's MAX_DOCS_TO_GRADE=2: -0.14 on 28 examples (about -5 here). Caught.
   - Deleting the refusal instruction from the generate prompt: -2 examples (0.921 -> 0.868). That is inside the hardware noise, so the eval cannot attribute it. The deterministic fast test (tests/test_graph_structure.py::test_generate_prompt_contains_refusal_instruction) catches it on every PR instead.

Why not tighter: at 0.03 (1 example) the gate would go red on any hardware or runtime change (point 2) and get switched off, the failure the brief warns about. Why not looser: 0.10+ would let a 4-example regression (about 10% of the set) through. The regression report lists every flipped example by id, even below the tolerance, so smaller changes are still visible in the PR comment without blocking it.

Cost: +20% mean cost per question fails the gate (stretch). The CPU path (extra retries from over-refusals) was +8%, the weakened prompt +6%.
