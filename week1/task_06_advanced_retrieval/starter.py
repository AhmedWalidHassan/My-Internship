"""
Task 6 — Advanced retrieval benchmark.

The harness (loader, baseline, question set, scorer) is provided.
Implement the build_*_retriever functions, then run:

    python task_06_advanced_retrieval/starter.py
"""

import functools
import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.utils import get_llm, get_embeddings, DATA_DIR


# --- provided: corpus + chunks ------------------------------------------------
def load_chunks():
    from langchain_community.document_loaders import TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    docs = []
    for md in sorted(DATA_DIR.glob("*.md")):
        docs.extend(TextLoader(md, encoding="utf-8").load())
    return RecursiveCharacterTextSplitter(
        chunk_size=600, chunk_overlap=80).split_documents(docs)

CHUNKS = load_chunks()

@functools.cache
def get_store():
    """Embed the corpus ONCE and share the FAISS store between every strategy.

    Before (Week 2 Task 1 stretch), each build_*_retriever call built its own index,
    so one benchmark run embedded the whole corpus 4 times."""
    from langchain_community.vectorstores import FAISS
    return FAISS.from_documents(CHUNKS, get_embeddings())


def build_baseline_retriever(k=4):
    return get_store().as_retriever(search_kwargs={"k": k})


# --- YOUR WORK: implement these ----------------------------------------------
def build_mmr_retriever(k=4):
    # TODO: same FAISS store but search_type="mmr".
    return get_store().as_retriever(search_type="mmr", search_kwargs={"k": k, "fetch_k": 20})


def build_multiquery_retriever(k=4):
    # TODO: wrap the baseline in MultiQueryRetriever.from_llm(retriever, llm=get_llm()).
    from langchain_classic.retrievers.multi_query import MultiQueryRetriever
    return MultiQueryRetriever.from_llm(retriever=build_baseline_retriever(k), llm=get_llm())

def build_hybrid_retriever(k=4):
    # TODO: EnsembleRetriever([bm25, dense], weights=[0.5, 0.5]).
    #       BM25Retriever.from_documents(CHUNKS) + the baseline dense retriever.
    from langchain_classic.retrievers.ensemble import EnsembleRetriever
    from langchain_community.retrievers import BM25Retriever   # needs: pip install rank_bm25
    bm25 = BM25Retriever.from_documents(CHUNKS)
    bm25.k = k
    dense = build_baseline_retriever(k)
    return EnsembleRetriever(retrievers=[bm25, dense], weights=[0.5, 0.5])
 

# --- provided: evaluation ----------------------------------------------------
# Each question is labeled with the file that SHOULD be retrieved.
QUESTIONS = [
    ("How many vacation days do full-time staff accrue?", "hr_policies.md,employee_handbook.md"),
    ("What do I do if my company laptop gets stolen?", "it_faq.md"),
    ("How fast can the rover go when carrying a load?", "product_specs.md"),
    ("What's the daily meal budget when traveling abroad?", "hr_policies.md"),
    ("How long is parental leave for an adoptive parent?", "employee_handbook.md"),
    ("How do I connect to the VPN from home?", "it_faq.md"),
]


def hit_rate(retriever):
    """Fraction of questions where a retrieved chunk came from a gold source file."""
    return score(retriever)[0]


def score(retriever):
    """(hit_rate, MRR). MRR = mean of 1/rank of the first chunk from a gold file
    (0 if none). Hit-rate ignores order; MRR rewards putting the right file FIRST.
    Caveat: MultiQueryRetriever returns a de-duplicated union in query order, not a
    ranking, so its MRR is only a rough signal."""
    hits, rr = 0, 0.0
    for question, gold in QUESTIONS:
        gold_files = set(gold.split(","))
        docs = retriever.invoke(question)
        ranks = [i for i, d in enumerate(docs, 1)
                 if Path(d.metadata.get("source", "")).name in gold_files]
        if ranks:
            hits += 1
            rr += 1 / ranks[0]
    return hits / len(QUESTIONS), rr / len(QUESTIONS)


if __name__ == "__main__":
    strategies = {
        "baseline": build_baseline_retriever,
        "mmr": build_mmr_retriever,
        "multiquery": build_multiquery_retriever,
        "hybrid": build_hybrid_retriever,
    }
    t0 = time.perf_counter()
    get_store()                                   # the only embedding pass of the corpus
    print(f"index built once in {time.perf_counter() - t0:.2f}s ({len(CHUNKS)} chunks)\n")
    print(f"{'strategy':<14} hit_rate   MRR   seconds")
    print("-" * 40)
    for name, builder in strategies.items():
        try:
            t = time.perf_counter()
            hr, mrr = score(builder())
            print(f"{name:<14} {hr:8.2f} {mrr:5.2f} {time.perf_counter() - t:9.2f}")
        except NotImplementedError:
            print(f"{name:<14} (not implemented yet)")
    print(f"\ntotal {time.perf_counter() - t0:.2f}s")
