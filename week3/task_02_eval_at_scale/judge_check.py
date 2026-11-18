"""
Task 2 — check the judge against a human, and test a stricter correctness prompt.

    python week3/task_02_eval_at_scale/judge_check.py week3/task_02_eval_at_scale/evidence/dev_full_run1.json

1. Agreement of the run's correctness verdicts with my 20 hand labels (human_labels.json).
2. Re-judges the SAME answers (no pipeline call) with the current CORRECTNESS_PROMPT and with the
   Week 2 one, on all examples of the run, and reports for each prompt: agreement with the 20
   labels, and agreement with the deterministic scorer on all of them (an independent floor: an
   answer missing a required fact can't be correct).
3. Groundedness probes: 3 answers with a planted unsupported claim (must be NO) and 3 faithful
   paraphrases (must be YES). A judge that says YES to a planted number can't catch a hallucination.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO), str(REPO / "week2" / "task_07_eval_gate" / "scripts")]

import run_eval  # noqa: E402

W2_CORRECTNESS_PROMPT = (     # the Week 2 judge prompt, verbatim, for comparison
    "You are grading an assistant's answer against a reference answer.\n"
    "Question: {question}\n"
    "Reference answer: {reference}\n"
    "Assistant answer: {answer}\n\n"
    "List the key facts (numbers, limits, conditions) that are needed to answer THE "
    "QUESTION ASKED and check whether the assistant answer states each one. Extra "
    "detail in the reference that the question did not ask for may be missing, and "
    "extra correct detail in the assistant answer is fine. Finish with a last line "
    "that says exactly 'VERDICT: CORRECT' if every needed fact is present and nothing "
    "contradicts the reference, otherwise 'VERDICT: INCORRECT'."
)

PROBES = [   # (context, answer, is the answer actually grounded?)
    ("[sick.pdf] Employees receive 10 paid sick days per calendar year.",
     "Employees receive 15 paid sick days per year.", False),
    ("[travel.pdf] Tier B (Egypt, India): meals $55 per day, hotel cap $150 per night.",
     "For Egypt the hotel cap is $150 per night and meals are $80 per day.", False),
    ("[vpn.pdf] Install Northwind Access from the Self-Service catalog and sign in with SSO.",
     "Install Northwind Access from the Self-Service catalog, sign in with SSO, and enter the PIN 4471.", False),
    ("[sick.pdf] Employees receive 10 paid sick days per calendar year, separate from PTO.",
     "You get ten paid sick days a year, and they are separate from your PTO.", True),
    ("[travel.pdf] Tier B (Egypt, India): meals $55 per day, hotel cap $150 per night.",
     "Egypt is a Tier B destination, so hotels are capped at $150 a night.", True),
    ("[r3.pdf] The maximum ramp incline is 5 degrees when loaded and 8 degrees when unloaded.",
     "A loaded R3 can climb ramps of up to 5 degrees.", True),
]


def main(argv) -> int:
    from app.capstone import load_capstone
    from app.config import get_settings

    run = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    labels = json.loads((HERE / "human_labels.json").read_text(encoding="utf-8"))["labels"]
    model = os.getenv("JUDGE_MODEL", "gemma3:4b")
    cap = load_capstone()
    judge = run_eval.make_judge(model, get_settings())
    data = {str(e["id"]): e for e in run_eval.load_dataset()}
    rows = [r for r in run["examples"] if "answer" in r]

    def verdict(prompt, r):
        ex = data[str(r["id"])]
        if ex["expect_refusal"] or cap.is_refusal(r["answer"]):         # same rule as make_evaluators
            return int(ex["expect_refusal"] and cap.is_refusal(r["answer"]))
        text = cap._ask(judge, prompt.format(question=run_eval.judge_question(ex),
                                            reference=ex["reference_answer"], answer=r["answer"]))
        found = [m.upper() for m in __import__("re").findall(r"VERDICT:\s*(INCORRECT|CORRECT)", text, flags=2)]
        return int(bool(found) and found[-1] == "CORRECT")

    out = {"judge": model, "run": argv[0], "from_run": {}, "prompts": {}}
    lab = {k: v["label"] for k, v in labels.items()}
    agree = [int(r["scores"]["correctness"] == lab[str(r["id"])]) for r in rows if str(r["id"]) in lab]
    out["from_run"] = {"human_agreement": f"{sum(agree)}/{len(agree)}"}
    for name, prompt in (("week2", W2_CORRECTNESS_PROMPT), ("current", cap.CORRECTNESS_PROMPT)):
        v = {str(r["id"]): verdict(prompt, r) for r in rows}
        human = [k for k in lab if k in v]
        det = [str(r["id"]) for r in rows]
        dis_h = [k for k in human if v[k] != lab[k]]
        out["prompts"][name] = {
            "correctness": round(sum(v.values()) / len(v), 3),
            "human_agreement": f"{len(human) - len(dis_h)}/{len(human)}", "human_disagreements": dis_h,
            "deterministic_agreement": f"{sum(v[k] == r['scores']['deterministic'] for k, r in zip(det, rows))}/{len(rows)}",
            "judge_correct_but_deterministic_fail": [k for k, r in zip(det, rows)
                                                     if v[k] == 1 and r["scores"]["deterministic"] == 0],
            "verdicts": v}
        print(name, {k: out["prompts"][name][k] for k in ("correctness", "human_agreement", "human_disagreements",
                                                           "deterministic_agreement", "judge_correct_but_deterministic_fail")},
              flush=True)
    probes = []
    for ctx, ans, truth in PROBES:
        ok, notes = cap.check_grounded(judge, ctx, ans)
        probes.append({"context": ctx, "answer": ans, "grounded": truth, "judge_says_grounded": ok,
                       "judge_right": ok == truth, "notes": notes[-300:]})
    out["groundedness_probes"] = probes
    print(f"groundedness probes: judge right on {sum(p['judge_right'] for p in probes)}/{len(probes)} "
          f"(planted claims caught {sum(p['judge_right'] for p in probes if not p['grounded'])}/3, "
          f"faithful paraphrases passed {sum(p['judge_right'] for p in probes if p['grounded'])}/3)")
    (HERE / "evidence" / "judge_check.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
