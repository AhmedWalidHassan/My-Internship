"""
Task 4 — the new fusion retriever (common/retrievers.py) must return EXACTLY the Week 2
EnsembleRetriever's rankings with the default settings, or every experiment is measured against a
moved baseline. Checks all dev questions at depth 4 (production) and 10 (the retrieval eval).

    python week3/task_04_retrieval_experiments/scripts/fusion_equivalence.py
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "week2" / "task_07_eval_gate" / "scripts")]
import run_eval  # noqa: E402

from app.capstone import load_capstone  # noqa: E402
from app.config import get_settings  # noqa: E402

cap = load_capstone()
from common.retrievers import build  # noqa: E402
from common.utils import get_embeddings  # noqa: E402
from langchain_classic.retrievers.ensemble import EnsembleRetriever  # noqa: E402
from langchain_community.retrievers import BM25Retriever  # noqa: E402

settings = get_settings()
store, _ = cap.ingest(get_embeddings(), settings.data_dir)
docs = list(store.docstore._dict.values())
examples = [e for e in run_eval.load_dataset() if e.get("split") == "dev"]
out = {}
for k in (4, 10):
    bm25 = BM25Retriever.from_documents(docs)
    bm25.k = k
    old = EnsembleRetriever(retrievers=[bm25, store.as_retriever(search_kwargs={"k": k})], weights=[0.5, 0.5])
    new, name = build(store, k, settings)
    # Week 3 Task 6: the production retriever only searches through an access scope. A scope holding every
    # group in the index sees every chunk, which is what the Week 2 retriever searched.
    new = new.for_scope({g for d in docs for g in str(d.metadata.get("acl_groups", "")).split(";") if g})
    diffs = []
    for ex in examples:
        q = run_eval.retrieval_query(ex)
        a = [d.page_content for d in old.invoke(q)]
        b = [d.page_content for d in new.invoke(q)]
        if a != b:
            diffs.append(ex["id"])
    out[f"k={k}"] = {"questions": len(examples), "identical": len(examples) - len(diffs), "different": diffs,
                     "retriever": name}
    print(k, out[f"k={k}"], flush=True)
(Path(__file__).resolve().parents[1] / "evidence" / "fusion_equivalence.json").write_text(json.dumps(out, indent=1))
