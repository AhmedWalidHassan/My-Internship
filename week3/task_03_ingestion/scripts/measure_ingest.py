"""
Task 3 — what a full and an incremental re-ingest cost (COST.md).

    CACHE_ENABLED=false python week3/task_03_ingestion/scripts/measure_ingest.py \
        --out week3/task_03_ingestion/evidence/ingest_cost.json

Works on a temporary COPY of week3/corpus (the export is upstream data: never edited in place)
and a temporary index, with the real embedding model and the embedding cache OFF, so every
embedding call is real:

1. full re-ingest (force rebuild): wall clock, chunks embedded, embedding tokens;
2. incremental: one document of the copy is edited (a sentence appended to
   product/R2/R2_End_of_Life_Notice.md, a small realistic edit), then `ingest()` runs again:
   wall clock, chunks re-embedded, tokens;
3. a no-change re-ingest (the warm start: 0 embedded).

Tokens: tiktoken cl100k_base over exactly the texts sent to the embedding model; dollars at
--price-per-1m (text-embedding-3-small, $0.02 / 1M). Locally the model is all-MiniLM-L6-v2: $0.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["CACHE_ENABLED"] = "false"
os.environ.setdefault("LANGSMITH_TRACING", "false")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from langchain_core.embeddings import Embeddings  # noqa: E402


class Counting(Embeddings):
    def __init__(self, inner):
        self.inner, self.texts = inner, []

    def embed_documents(self, texts):
        self.texts.extend(texts)
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        return self.inner.embed_query(text)

    @property
    def model_name(self):                       # same index signature as the real model
        inner = getattr(self.inner, "inner", self.inner)
        return getattr(inner, "model_name", type(inner).__name__)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--price-per-1m", type=float, default=0.02)
    args = ap.parse_args(argv)

    import tiktoken

    from app.capstone import load_capstone

    enc = tiktoken.get_encoding("cl100k_base")
    cap = load_capstone()                       # puts week1/ (common.*) on sys.path
    from common.utils import get_embeddings
    work = Path(tempfile.mkdtemp(prefix="nw_ingest_cost_"))
    corpus = work / "corpus"
    shutil.copytree(REPO / "week3" / "corpus", corpus)
    cap.INDEX_DIR, cap.MANIFEST_PATH = work / "index", work / "index" / "manifest.json"
    emb = Counting(get_embeddings())
    emb.embed_query("warm-up")                  # model load is not ingestion

    def run(name, **kw):
        before = len(emb.texts)
        t0 = time.perf_counter()
        store, stats = cap.ingest(emb, corpus, **kw)
        secs = time.perf_counter() - t0
        texts = emb.texts[before:]
        tokens = sum(len(enc.encode(t)) for t in texts)
        row = {"run": name, "wall_clock_s": round(secs, 2), "chunks_embedded": len(texts), "embedding_tokens": tokens,
               "cost_usd_at_price": round(tokens / 1e6 * args.price_per_1m, 6), "documents": stats["documents"],
               "chunks_in_index": stats["chunks"], "added": len(stats["added"]), "updated": stats["updated"],
               "reused": len(stats["reused"]), "skipped": len(stats["skipped"])}
        print(row, flush=True)
        return row

    rows = [run("full re-ingest (force rebuild)", force=True)]
    doc = corpus / "product" / "R2" / "R2_End_of_Life_Notice.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nTrade-in requests go through your account manager.\n",
                   encoding="utf-8")
    rows.append(run("incremental: one changed document (R2_End_of_Life_Notice.md)"))
    rows.append(run("no change (warm start)"))
    try:
        import torch
        device = f"cuda ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "cpu"
    except Exception:
        device = "unknown"
    index_bytes = sum(p.stat().st_size for p in (work / "index").rglob("*") if p.is_file())
    out = {"device": device, "embedding_model": emb.model_name, "price_per_1m_tokens": args.price_per_1m,
           "index_bytes": index_bytes, "runs": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
