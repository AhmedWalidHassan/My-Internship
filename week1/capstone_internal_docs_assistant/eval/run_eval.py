"""Evaluation harness: correctness, groundedness and retrieval hit-rate.

    python capstone_internal_docs_assistant/eval/run_eval.py --note "baseline"
    python capstone_internal_docs_assistant/eval/run_eval.py --retriever mmr --note "mmr instead of hybrid"
    python capstone_internal_docs_assistant/eval/run_eval.py --local      # no LangSmith, plain loop

With LangSmith configured, the dataset is created on first run and every run
becomes a named experiment you can open and inspect per example. Either way the
scores are written into EVAL_RESULTS.md and the per-example detail goes to
eval/last_run.json (use it for your failure analysis).

Dataset: eval/dataset.json (yours; create it with eval/generate_dataset.py and review it).
If it doesn't exist and you are indexing the bundled sample_data/, eval/dataset_sample.json is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import settings  # noqa: E402
from backend import RagBackend  # noqa: E402

DATASET_NAME = "northwind-capstone"  # delete it in LangSmith after editing dataset.json
RESULTS_MD = HERE.parent / "EVAL_RESULTS.md"
SCORES: dict[str, list] = defaultdict(list)   # metric -> [score | None]
DETAIL: dict[str, dict] = {}                  # question -> everything we know

CORRECT_PROMPT = """You are grading a question-answering system.

Question: {question}
Reference answer: {reference}
System answer: {answer}

Is the system answer correct, i.e. it states the key facts of the reference answer and does not contradict it? Reply with exactly one word: CORRECT or INCORRECT."""

GROUNDED_PROMPT = """You are checking an answer for hallucinations.

Context passages:
{context}

Answer: {answer}

Is every factual claim in the answer supported by the context passages? Reply with exactly one word: YES or NO."""


def _verdict(text: str, positive: str) -> int:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip().upper()
    return int(text.startswith(positive) and not text.startswith("IN" + positive))


def make_evaluators(judge):
    def record(key, question, score, comment=""):
        SCORES[key].append(score)
        DETAIL.setdefault(question, {})[key] = score
        return {"key": key, "score": score, "comment": comment}

    def correctness(inputs, outputs, reference_outputs):
        q = inputs["question"]
        if reference_outputs["type"] == "out_of_scope":
            return record("correctness", q, int(outputs["refused"]), "out-of-scope: must refuse")
        if outputs["refused"]:
            return record("correctness", q, 0, "refused an answerable question")
        raw = judge.invoke(CORRECT_PROMPT.format(question=q, reference=reference_outputs["reference"], answer=outputs["answer"])).content
        return record("correctness", q, _verdict(raw, "CORRECT"), raw.strip()[:200])

    def groundedness(inputs, outputs, reference_outputs):
        q = inputs["question"]
        if outputs["refused"]:
            return record("groundedness", q, 1, "refusal makes no claims")
        context = "\n\n".join(outputs["contexts"]) or "(none)"
        raw = judge.invoke(GROUNDED_PROMPT.format(context=context, answer=outputs["answer"])).content
        return record("groundedness", q, _verdict(raw, "YES"), raw.strip()[:200])

    def retrieval_hit(inputs, outputs, reference_outputs):
        q = inputs["question"]
        expected = set(reference_outputs.get("expected_sources", []))
        if not expected:
            SCORES["retrieval_hit"].append(None)  # n/a for out-of-scope
            return {"key": "retrieval_hit", "score": None, "comment": "n/a (out-of-scope)"}
        hit = int(expected <= set(outputs["retrieved_sources"]))
        return record("retrieval_hit", q, hit, f"expected {sorted(expected)}, got {outputs['retrieved_sources']}")

    return [correctness, groundedness, retrieval_hit]


def load_dataset(path: str | None = None) -> list[dict]:
    if path:
        f = Path(path)
    elif (HERE / "dataset.json").exists():
        f = HERE / "dataset.json"
    elif settings.DATA_DIR.name == "sample_data":
        f = HERE / "dataset_sample.json"
    else:
        sys.exit(
            f"No eval/dataset.json for your corpus ({settings.DATA_DIR}).\n"
            "Draft one with:  python capstone_internal_docs_assistant/eval/generate_dataset.py\n"
            "then review/edit it and re-run."
        )
    print(f"[eval] dataset: {f.name}")
    return json.loads(f.read_text(encoding="utf-8"))


def ensure_langsmith_dataset(client, rows: list[dict]) -> None:
    if client.has_dataset(dataset_name=DATASET_NAME):
        print(f"[eval] reusing LangSmith dataset '{DATASET_NAME}' (delete it in the UI to re-upload edited examples)")
        return
    ds = client.create_dataset(DATASET_NAME, description="Northwind capstone eval set")
    inputs = [{"question": r["question"]} for r in rows]
    outputs = [{"reference": r["reference"], "expected_sources": r["expected_sources"], "type": r["type"]} for r in rows]
    try:  # newer langsmith
        client.create_examples(dataset_id=ds.id, examples=[{"inputs": i, "outputs": o} for i, o in zip(inputs, outputs)])
    except TypeError:  # older langsmith
        client.create_examples(inputs=inputs, outputs=outputs, dataset_id=ds.id)
    print(f"[eval] created dataset '{DATASET_NAME}' with {len(rows)} examples")


def mean(values):
    vals = [v for v in values if v is not None]
    return (sum(vals) / len(vals)) if vals else float("nan")


def write_results(args, experiment: str, n: int, model_name: str) -> None:
    c, g, h = (mean(SCORES[k]) for k in ("correctness", "groundedness", "retrieval_hit"))
    n_ans = sum(1 for v in SCORES["retrieval_hit"] if v is not None)
    latest = f"""## Latest experiment
- **Date:** {dt.date.today().isoformat()}
- **LangSmith experiment name/link:** {experiment}
- **Dataset size:** {n} examples ({n - n_ans} out-of-scope)
- **Retriever used:** {args.retriever or settings.RETRIEVER_MODE}
- **Model:** {model_name} (judge: {args.judge_model or model_name})

## Scores
| Metric | Score |
|--------|-------|
| Correctness | {c:.2f} |
| Groundedness / faithfulness | {g:.2f} |
| Retrieval hit-rate | {h:.2f} (answerable questions only) |

"""
    template = RESULTS_MD.read_text(encoding="utf-8") if RESULTS_MD.exists() else ""
    if "## Latest experiment" in template and "## Failure analysis" in template:
        head, rest = template.split("## Latest experiment", 1)
        _, tail = rest.split("## Failure analysis", 1)
        text = head + latest + "## Failure analysis" + tail
    else:
        text = "# Capstone Evaluation Results\n\n" + latest + "## Failure analysis\n- **Biggest failure mode observed:**\n- **Root cause (retrieval vs. generation vs. prompt):**\n- **What I would change next to fix it:**\n\n## Experiment log (optional but encouraged)\n| # | Change made | Correctness | Groundedness | Notes |\n|---|-------------|-------------|--------------|-------|\n"
    # drop unfilled template rows like "| 1 | baseline | | | |"
    lines = [l for l in text.splitlines() if not re.match(r"\|\s*\d+\s*\|[^|]*\|\s*\|\s*\|[^|]*\|\s*$", l)]
    next_no = len([l for l in lines if re.match(r"\|\s*\d+\s*\|", l)]) + 1
    new_row = f"| {next_no} | {args.note or (args.retriever or settings.RETRIEVER_MODE)} | {c:.2f} | {g:.2f} | hit-rate {h:.2f} |"
    RESULTS_MD.write_text("\n".join(lines).rstrip() + "\n" + new_row + "\n", encoding="utf-8")
    print(f"[eval] wrote {RESULTS_MD.name}: correctness={c:.2f} groundedness={g:.2f} retrieval_hit={h:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retriever", choices=["hybrid", "mmr", "similarity"], help="override RETRIEVER_MODE")
    ap.add_argument("--note", help="short description for the experiment log row")
    ap.add_argument("--local", action="store_true", help="skip LangSmith, run a plain loop")
    ap.add_argument("--judge-model", help="override the judge model (same provider)")
    ap.add_argument("--dataset", help="path to a dataset json (default: eval/dataset.json)")
    args = ap.parse_args()

    rows = load_dataset(args.dataset)
    print(f"[eval] corpus: {settings.DATA_DIR}")

    backend = RagBackend(retriever_mode=args.retriever)
    judge = settings.get_llm(model=args.judge_model) if args.judge_model else settings.get_llm()
    evaluators = make_evaluators(judge)

    def target(inputs: dict) -> dict:
        res = backend.invoke(inputs["question"], session_id=str(uuid.uuid4()))  # fresh memory per example
        DETAIL.setdefault(inputs["question"], {}).update(answer=res["answer"], refused=res["refused"], retrieved=res["retrieved_sources"], sources=res["sources"])
        return {k: res[k] for k in ("answer", "refused", "contexts", "retrieved_sources", "sources")}

    experiment = "(local run, not logged to LangSmith)"
    use_langsmith = not args.local and settings.tracing_enabled()
    if not args.local and not use_langsmith:
        print("[eval] LangSmith tracing/API key not configured -> running locally. Set LANGSMITH_* in .env for tracked experiments.")

    if use_langsmith:
        from langsmith import Client, evaluate

        client = Client()
        ensure_langsmith_dataset(client, rows)
        results = evaluate(
            target,
            data=DATASET_NAME,
            evaluators=evaluators,
            experiment_prefix=f"northwind-{args.retriever or settings.RETRIEVER_MODE}",
            max_concurrency=1,  # local Ollama: one request at a time
            metadata={"retriever": args.retriever or settings.RETRIEVER_MODE, "note": args.note or ""},
        )
        experiment = getattr(results, "experiment_name", "see LangSmith > Datasets & Experiments")
    else:
        for i, row in enumerate(rows, 1):
            print(f"[eval] {i}/{len(rows)} {row['question']}")
            out = target({"question": row["question"]})
            ref = {k: row[k] for k in ("reference", "expected_sources", "type")}
            for ev in evaluators:
                ev({"question": row["question"]}, out, ref)

    model_name = settings.OLLAMA_MODEL if settings.LLM_PROVIDER == "ollama" else settings.LLM_PROVIDER
    write_results(args, experiment, len(rows), model_name)
    (HERE / "last_run.json").write_text(json.dumps(DETAIL, indent=2, ensure_ascii=False), encoding="utf-8")
    failures = [q for q, d in DETAIL.items() if d.get("correctness") == 0 or d.get("groundedness") == 0 or d.get("retrieval_hit") == 0]
    print(f"[eval] {len(failures)} examples with at least one failing metric -> see eval/last_run.json")


if __name__ == "__main__":
    main()
