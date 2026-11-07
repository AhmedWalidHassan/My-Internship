"""Draft eval questions from YOUR indexed documents.

    python capstone_internal_docs_assistant/eval/generate_dataset.py --n 22

For a spread of chunks across all files, the local LLM writes one question that
only that passage can answer plus a short reference answer. A few generic
out-of-scope questions are appended (the assistant must refuse those).
The result is eval/dataset.json -- REVIEW AND EDIT IT: a 4B model writes some
mediocre or ambiguous questions, and a bad reference answer makes a good
assistant look wrong. Delete or fix those rows before trusting any score.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import settings  # noqa: E402
from ingestion import IndexManager  # noqa: E402

PROMPT = """Read the passage from a company document and write ONE question that an employee could ask and that this passage answers with a specific fact (a number, name, date or rule). Do not mention "the passage" or "the document" in the question. Then give the short correct answer.

Passage:
{passage}

Reply in exactly this format:
Q: <question>
A: <short answer>"""

OUT_OF_SCOPE = [
    "How do I cook spaghetti carbonara?",
    "Who won the most recent football World Cup?",
    "What is the CEO's personal salary?",
    "What will the weather be like tomorrow?",
    "Can you recommend a good movie to watch tonight?",
]


def parse(text: str):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    q = re.search(r"^\s*Q:\s*(.+)$", text, re.M)
    a = re.search(r"^\s*A:\s*(.+)$", text, re.M)
    return (q.group(1).strip(), a.group(1).strip()) if q and a else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=22, help="number of answerable questions")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "dataset.json"))
    args = ap.parse_args()

    mgr = IndexManager()
    mgr.sync()
    by_file: dict[str, list] = {}
    for doc in mgr.vectorstore.docstore._dict.values():
        if len(doc.page_content) > 150:  # skip tiny heading-only chunks
            by_file.setdefault(doc.metadata["source"], []).append(doc)

    rng = random.Random(args.seed)
    for docs in by_file.values():
        rng.shuffle(docs)
    # round-robin over files so every document is covered
    picks, files = [], list(by_file)
    while len(picks) < args.n and any(by_file.values()):
        for f in files:
            if by_file[f] and len(picks) < args.n:
                picks.append(by_file[f].pop())

    llm = settings.get_llm()
    rows = []
    for i, doc in enumerate(picks, 1):
        parsed = parse(llm.invoke(PROMPT.format(passage=doc.page_content)).content)
        print(f"[gen] {i}/{len(picks)} {doc.metadata['source']}: {parsed[0] if parsed else 'SKIPPED (unparseable)'}")
        if parsed:
            rows.append({"question": parsed[0], "reference": parsed[1],
                         "expected_sources": [doc.metadata["source"]], "type": "answerable"})
    for q in OUT_OF_SCOPE:
        rows.append({"question": q, "reference": "Not in the documents; the assistant should decline.",
                     "expected_sources": [], "type": "out_of_scope"})
    Path(args.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[gen] wrote {len(rows)} rows to {args.out}. Now review/edit them before running run_eval.py.")


if __name__ == "__main__":
    main()
