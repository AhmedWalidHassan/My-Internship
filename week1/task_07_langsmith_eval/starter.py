"""
Task 7 — LangSmith evaluation.

Prereq: LANGCHAIN_API_KEY and LANGCHAIN_TRACING_V2=true set in .env.

Run with:  python task_07_langsmith_eval/starter.py
"""

import json
import sys
from pathlib import Path
import importlib.util
import re

sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.utils import get_llm

# Reuse your Task 4 pipeline as the system-under-test.
sys.path.append(str(Path(__file__).resolve().parents[1] / "task_04_naive_rag"))
def _load_task4():
    path = Path(__file__).resolve().parents[1] / "task_04_naive_rag" / "starter.py"
    spec = importlib.util.spec_from_file_location("task04_rag", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

DATASET_PATH = Path(__file__).resolve().parent / "eval_dataset.jsonl"
DATASET_NAME = "rag-internship-eval"


def load_examples():
    with open(DATASET_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def ensure_dataset(client):
    """Create the LangSmith dataset if it doesn't exist, and upload examples."""
    from langsmith import Client  # noqa

    # TODO 1: If the dataset doesn't exist, client.create_dataset(DATASET_NAME),
    #         then client.create_examples(...) with inputs={"question": ...}
    #         and outputs={"answer": ...} from load_examples().
    if client.has_dataset(dataset_name=DATASET_NAME):
        return
    examples = load_examples()
    ds = client.create_dataset(DATASET_NAME, description="Northwind RAG eval set")
    client.create_examples(
        dataset_id=ds.id,
        inputs=[{"question": e["question"]} for e in examples],
        outputs=[{"answer": e["answer"], "source": e["source"]} for e in examples],
    )

_task4 = _load_task4()
_retriever = _task4.build_retriever(k=4)
_rag_chain = _task4.build_rag_chain(_retriever)

def target(inputs: dict) -> dict:
    """Adapter: LangSmith passes {'question': ...}; return {'answer': ...}."""
    # TODO 2: Build your RAG chain (from Task 4) once, then:
    #         return {"answer": rag_chain.invoke(inputs["question"])}
    question = inputs["question"]
    docs = _retriever.invoke(question)          # what the chain will see
    answer = _rag_chain.invoke(question)
    return {
        "answer": answer,
        "context": _task4.format_docs(docs),
        "sources": sorted({Path(d.metadata.get("source", "")).name for d in docs}),
    }
    raise NotImplementedError

def _verdict(text: str):
    """Take the judge's last verdict word; ignore any <think> block."""
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S).upper()
    found = re.findall(r"\b(INCORRECT|CORRECT|UNGROUNDED|GROUNDED)\b", text)
    return found[-1] if found else None

def make_evaluators():
    """Return a list of evaluators for correctness and groundedness."""
    judge = get_llm()

    # TODO 3: Define two evaluators. Simplest path is the openevals / built-in
    #         LLM-as-judge helpers, or write your own function evaluators that
    #         return {"key": "correctness", "score": 0..1}.
    #         - correctness: compare outputs['answer'] to reference answer
    #         - groundedness: is the answer supported by the source docs?
    def correctness(inputs, outputs, reference_outputs):
        prompt = (
            "You are grading an answer against a reference answer.\n"
            f"Question: {inputs['question']}\n"
            f"Reference answer: {reference_outputs['answer']}\n"
            f"Model answer: {outputs['answer']}\n\n"
            "Ignore any list of source files in the model answer. Is the model "
            "answer consistent with the reference and does it contain the same key "
            "facts and numbers? Reply with exactly one word: CORRECT or INCORRECT."
        )
        reply = judge.invoke(prompt).content
        v = _verdict(reply)
        return {"key": "correctness", "score": 1 if v == "CORRECT" else 0,
                "comment": f"verdict={v}; raw={str(reply)[:200]}"}

    def groundedness(inputs, outputs):
        prompt = (
            f"Context:\n{outputs['context']}\n\n"
            f"Answer:\n{outputs['answer']}\n\n"
            "Is every factual claim in the answer supported by the context above? "
            "Ignore the list of source files. An answer that says it does not know "
            "counts as GROUNDED. Reply with exactly one word: GROUNDED or UNGROUNDED."
        )
        reply = judge.invoke(prompt).content
        v = _verdict(reply)
        return {"key": "groundedness", "score": 1 if v == "GROUNDED" else 0,
                "comment": f"verdict={v}; raw={str(reply)[:200]}"}

    # Bonus, no LLM: did retrieval even fetch the right file?
    def retrieval_hit(outputs, reference_outputs):
        hit = reference_outputs["source"] in outputs["sources"]
        return {"key": "retrieval_hit", "score": 1 if hit else 0}

    return [correctness, groundedness, retrieval_hit]


if __name__ == "__main__":
    from langsmith import Client
    from langsmith import evaluate

    client = Client()
    ensure_dataset(client)

    # TODO 4: Call evaluate(target, data=DATASET_NAME,
    #                        evaluators=make_evaluators(),
    #                        experiment_prefix="naive-rag")
    #         Then open the printed URL in LangSmith to inspect results.
    results = evaluate(
        target,
        data=DATASET_NAME,
        evaluators=make_evaluators(),
        experiment_prefix="naive-rag",
        max_concurrency=1,          # one local model + one 6 GB GPU: go sequentially
    )

    scores = {}
    for row in results:
        for er in row["evaluation_results"]["results"]:
            scores.setdefault(er.key, []).append(er.score)
    print()
    for key, vals in scores.items():
        print(f"{key:<14} {sum(vals) / len(vals):.2f}  ({len(vals)} examples)")
