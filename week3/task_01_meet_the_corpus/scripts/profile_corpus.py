"""
Task 1 — profile the Week 3 corpus as the Week 2 system sees it, and measure what it
costs to embed.

    python week3/task_01_meet_the_corpus/scripts/profile_corpus.py \
        --out week3/task_01_meet_the_corpus/evidence/corpus_profile
    CUDA_VISIBLE_DEVICES= python .../profile_corpus.py --out .../corpus_profile_cpu   # CPU timing

Three views of the same 190 documents:

  literal    the UNCHANGED Week 2 loader on DATA_DIR=week3/corpus: `iterdir()`, top level,
             .md/.txt only. What `docker compose up` / `make run` would index.
  recursive  the same loader fed every .md/.txt under the corpus (corpus_view.py): what the
             Week 2 chunker and retriever can read at all without a new parser.
  full       every document, text pulled out with a naive reference extractor (PyMuPDF for
             PDF, BeautifulSoup get_text() on the WHOLE page for HTML, openpyxl rows for
             XLSX, raw CSV), then chunked by the same Week 2 chunker (800/100). This is
             "embed the whole corpus once"; the extractor is for measurement, NOT the product
             loader (that is Task 3).

Embedding is measured, not estimated: each view is indexed with the real Week 2 `ingest()`
(same embedding model, FAISS, force rebuild, embedding cache OFF so nothing is reused),
timed, and the index size on disk is taken from the files written. Tokens are counted with
tiktoken cl100k_base (the tokenizer of OpenAI's text-embedding-3 models) over exactly the
chunk texts that get embedded, and priced at --price-per-1m (default $0.02 / 1M tokens,
text-embedding-3-small list price). Locally the model is all-MiniLM-L6-v2: actual spend $0.

It also prints programmatic evidence for the data-quality issues in RESULTS.md (ligatures,
IDs split across lines, OCR substitutions, boilerplate, near duplicates, date anomalies).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ["CACHE_ENABLED"] = "false"            # measure real embedding work, never a cache hit
os.environ.setdefault("LANGSMITH_TRACING", "false")

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS = REPO_ROOT / "week3" / "corpus"
W2_DATA = REPO_ROOT / "week1" / "data"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_view import W2_SUPPORTED_EXT, build_view  # noqa: E402

LIGATURES = re.compile("[ﬀ-ﬆ]")
MONTHS = "January February March April May June July August September October November December".split()


# ---------------------------------------------------------------------------
# Reference extraction (measurement only)
# ---------------------------------------------------------------------------
def extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        import pymupdf
        with pymupdf.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    if ext == ".html":
        from bs4 import BeautifulSoup
        return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser").get_text("\n", strip=True)
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        lines = []
        for ws in wb.worksheets:
            lines.append(f"## {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(c is not None for c in row):
                    lines.append(" | ".join("" if c is None else str(c) for c in row))
        return "\n".join(lines)
    return path.read_text(encoding="utf-8", errors="replace")


def detect_language(text: str) -> str:
    from langdetect import DetectorFactory, detect
    DetectorFactory.seed = 0
    try:
        return detect(text[:5000]) if text.strip() else "empty"
    except Exception:
        return "unknown"


def tokens(texts: list[str]) -> int:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    return sum(len(enc.encode(t)) for t in texts)


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# Measured index builds with the real Week 2 ingest()
# ---------------------------------------------------------------------------
def measure_build(cap, embeddings, data_dir: Path, name: str, price_per_1m: float) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"nw_index_{re.sub(r'\W+', '_', name)}_"))
    cap.INDEX_DIR, cap.MANIFEST_PATH = tmp / "faiss_index", tmp / "faiss_index" / "manifest.json"
    t0 = time.perf_counter()
    store, stats = cap.ingest(embeddings, data_dir, force=True)
    seconds = time.perf_counter() - t0
    chunks = [d.page_content for d in store.docstore._dict.values()]
    n_tok = tokens(chunks)
    out = {"view": name, "files": len(stats["added"]), "chunks": len(chunks),
           "chars": sum(len(c) for c in chunks), "embedding_tokens": n_tok,
           "index_build_s": round(seconds, 2), "index_bytes": dir_size(tmp / "faiss_index"),
           "cost_usd_at_price": round(n_tok / 1e6 * price_per_1m, 6)}
    shutil.rmtree(tmp, ignore_errors=True)
    return out


# ---------------------------------------------------------------------------
# Data-quality evidence
# ---------------------------------------------------------------------------
def quality_checks(texts: dict[str, str], meta: dict[str, dict], cap) -> dict:
    ev = {}
    pdf = {p: t for p, t in texts.items() if p.endswith(".pdf")}
    ev["pdf_ligatures"] = {"docs": sum(1 for t in pdf.values() if LIGATURES.search(t)), "of": len(pdf),
                           "occurrences": sum(len(LIGATURES.findall(t)) for t in pdf.values()),
                           "examples": sorted({w for t in pdf.values() for w in re.findall(r"\w*[ﬀ-ﬆ]\w*", t)})[:12]}
    split_ids = {}
    for p, t in pdf.items():
        hits = re.findall(r"\b([A-Z]{2,3}-)\n([A-Z]{2,5}[-\w]*)", t)
        if hits:
            split_ids[p] = ["".join(h).replace("\n", "") for h in hits]
    ev["ids_split_across_lines"] = split_ids
    scans = {p: t for p, t in texts.items() if p.startswith("scanned_archive/")}
    ev["ocr_suspect_tokens"] = {p: sorted(set(re.findall(r"\$?\b(?=\w*[A-Za-z])(?=\w*\d)\w+\b", t)) -
                                          {"R2", "R3"}) for p, t in scans.items()}
    # boilerplate: share of the manual's sentences that are repeats of another sentence
    manual = texts.get("product/R3/R3_Operator_Manual_RevC.pdf", "")
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", manual)) if len(s.strip()) > 30]
    c = Counter(sents)
    ev["manual_boilerplate"] = {"sentences": len(sents), "distinct": len(c),
                                "share_that_are_repeats": round(1 - len(c) / max(len(sents), 1), 3),
                                "top": [(s[:80], n) for s, n in c.most_common(3)]}
    # repeated page furniture in PDFs (known issue: quantified)
    furniture = Counter()
    for t in pdf.values():
        for line in set(t.splitlines()):
            if re.search(r"Page \d+ of \d+|Controlled copy|do not distribute|Product Data Sheet", line):
                furniture[re.sub(r"\d+", "N", line.strip())] += 1
    ev["pdf_furniture_lines"] = furniture.most_common(5)
    # wiki chrome share (known issue: quantified)
    from bs4 import BeautifulSoup
    full = content = 0
    for p in meta:
        if p.endswith(".html") and p.startswith("wiki/"):
            s = BeautifulSoup((CORPUS / p).read_text(encoding="utf-8"), "html.parser")
            full += len(s.get_text(" ", strip=True))
            body = s.find(class_="content")
            content += len(body.get_text(" ", strip=True)) if body else 0
    ev["wiki_chrome_share"] = round(1 - content / full, 3) if full else None
    # dates in the text that are later than the document's last_modified
    later = []
    for p, t in texts.items():
        lm = meta[p]["last_modified"]
        for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\s+(20\d\d)\b", t):
            iso = f"{m.group(2)}-{MONTHS.index(m.group(1)) + 1:02d}"
            if iso > lm[:7] and not re.search(r"(will|until|by|end|effective|from|before|due|ends?)\s*$",
                                              t[max(0, m.start() - 25):m.start()], re.I):
                later.append({"doc": p, "last_modified": lm, "mentions": m.group(0),
                              "context": re.sub(r"\s+", " ", t[max(0, m.start() - 70):m.end() + 10])})
    ev["text_dated_after_last_modified"] = later
    # BOMs and lexical traps
    ev["utf8_bom"] = [p for p in meta if (CORPUS / p).read_bytes()[:3] == b"\xef\xbb\xbf"]
    meet = {p: t for p, t in texts.items() if p.startswith("meetings/")}
    ev["meetings_lexical_traps"] = {
        term: {"docs": sum(1 for t in meet.values() if re.search(term, t, re.I)), "of": len(meet)}
        for term in (r"carry.over", r"\bPTO\b", r"\bVPN\b", r"password")}
    # near-duplicate chunks (MinHash over word 3-shingles of the full view's chunks)
    from datasketch import MinHash, MinHashLSH
    lsh, sigs, owner = MinHashLSH(threshold=0.8, num_perm=64), {}, {}
    k = 0
    for p, t in texts.items():
        tmp = Path(tempfile.mkdtemp()) / (Path(p).stem + ".txt")
        tmp.write_text(t, encoding="utf-8")
        for ch in cap.chunk_file(tmp):
            words = ch.page_content.lower().split()
            m = MinHash(num_perm=64)
            for sh in {" ".join(words[i:i + 3]) for i in range(max(len(words) - 2, 1))}:
                m.update(sh.encode())
            key = f"c{k}"
            k += 1
            lsh.insert(key, m)
            sigs[key], owner[key] = m, p
        shutil.rmtree(tmp.parent, ignore_errors=True)
    dup_pairs = set()
    for key, m in sigs.items():
        for other in lsh.query(m):
            if other != key:
                dup_pairs.add(tuple(sorted((key, other))))
    by_doc = Counter()
    cross = Counter()
    for a, b in dup_pairs:
        if owner[a] == owner[b]:
            by_doc[owner[a]] += 1
        else:
            cross[tuple(sorted((owner[a], owner[b])))] += 1
    ev["near_duplicate_chunks"] = {"chunks": k, "pairs_jaccard_ge_0.8": len(dup_pairs),
                                   "chunks_involved": len({c for pair in dup_pairs for c in pair}),
                                   "within_doc_top": by_doc.most_common(5),
                                   "cross_doc_top": [(f"{a} ~ {b}", n) for (a, b), n in cross.most_common(8)]}
    return ev


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="output path without extension (.json + .md)")
    ap.add_argument("--price-per-1m", type=float, default=0.02, help="embedding $ per 1M tokens")
    ap.add_argument("--skip-builds", action="store_true", help="profile only, no timed index builds")
    args = ap.parse_args(argv)

    from app.capstone import load_capstone
    from app.config import get_settings

    cap = load_capstone()
    settings = get_settings()
    meta = {r["path"]: r for r in csv.DictReader(open(CORPUS / "_metadata.csv", encoding="utf-8"))}
    literal = {p.name for p in CORPUS.iterdir() if p.suffix.lower() in W2_SUPPORTED_EXT}   # what iterdir() sees

    docs, texts = [], {}
    view_tmp = Path(tempfile.mkdtemp(prefix="nw_full_view_"))
    for rel, m in sorted(meta.items()):
        path = CORPUS / rel
        ext = path.suffix.lower()
        text = extract(path)
        texts[rel] = text
        (view_tmp / f"{path.stem}{ext.replace('.', '_')}.txt").write_text(text, encoding="utf-8")
        readable = ext in W2_SUPPORTED_EXT
        w2_chunks = cap.chunk_file(path) if readable else []
        docs.append({"path": rel, "source_system": m["source_system"], "format": ext.lstrip("."),
                     "acl": m["acl_groups"], "bytes": path.stat().st_size,
                     "w2_literal": "loaded" if rel in literal else "skipped silently (not at top level)",
                     "w2_recursive": "loaded" if readable else f"skipped silently (.{ext.lstrip('.')} not in SUPPORTED_EXT)",
                     "w2_chars": len(path.read_text(encoding="utf-8")) if readable else 0,
                     "w2_chunks": len(w2_chunks), "full_chars": len(text), "language": detect_language(text)})

    def tally(key):
        t = defaultdict(lambda: Counter())
        for d in docs:
            t[d[key]]["total"] += 1
            t[d[key]]["recursive_loaded"] += d["w2_recursive"] == "loaded"
            t[d[key]]["literal_loaded"] += d["w2_literal"] == "loaded"
            t[d[key]]["w2_chunks"] += d["w2_chunks"]
            t[d[key]]["full_chars"] += d["full_chars"]
        return {k: dict(v) for k, v in sorted(t.items(), key=lambda kv: -kv[1]["total"])}

    profile = {
        "settings": {"chunking": f"{settings.chunk_size}/{settings.chunk_overlap}",
                     "embedding_model": settings.hf_embed_model if settings.embedding_provider != "openai"
                     else settings.openai_embed_model, "price_per_1m_tokens": args.price_per_1m},
        "documents": len(docs),
        "literal": {"top_level_files_indexed": sorted(literal), "metadata_docs_loaded": 0},
        "by_source_system": tally("source_system"),
        "by_format": tally("format"),
        "languages": dict(Counter(d["language"] for d in docs)),
        "totals": {"recursive_loaded": sum(d["w2_recursive"] == "loaded" for d in docs),
                   "recursive_chars": sum(d["w2_chars"] for d in docs),
                   "recursive_chunks": sum(d["w2_chunks"] for d in docs),
                   "full_chars": sum(d["full_chars"] for d in docs)},
        "per_document": docs,
    }

    if not args.skip_builds:
        try:
            import torch
            device = f"cuda ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "unknown"
        from common.utils import get_embeddings
        print(f"Loading embeddings ({device}) ...", flush=True)
        t0 = time.perf_counter()
        emb = get_embeddings()
        emb.embed_query("warm-up")                                   # model load + first call not counted
        load_s = time.perf_counter() - t0
        lit_dir = Path(tempfile.mkdtemp(prefix="nw_literal_"))
        for name in literal:
            (lit_dir / name).symlink_to(CORPUS / name)
        rec_dir, _ = build_view(CORPUS, Path(tempfile.mkdtemp(prefix="nw_recursive_")) / "view")
        builds = []
        for name, d in (("week2 corpus (week1/data)", W2_DATA), ("literal (W2 loader, week3/corpus)", lit_dir),
                        ("recursive (W2 loader, all .md/.txt)", rec_dir), ("full (all 190, reference extractor)", view_tmp)):
            print(f"  building {name} ...", flush=True)
            builds.append(measure_build(cap, emb, d, name, args.price_per_1m))
            print(f"    {builds[-1]}", flush=True)
        profile["embedding"] = {"device": device, "model_load_s": round(load_s, 2), "builds": builds}

    print("Data-quality checks ...", flush=True)
    profile["quality_evidence"] = quality_checks(texts, meta, cap)
    shutil.rmtree(view_tmp, ignore_errors=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".json").write_text(json.dumps(profile, indent=1, ensure_ascii=False), encoding="utf-8")
    args.out.with_suffix(".md").write_text(render(profile), encoding="utf-8")
    print(render(profile))
    print(f"wrote {args.out.with_suffix('.json')} and .md")
    return 0


def render(p: dict) -> str:
    L = ["# Corpus profile", "",
         f"Chunking {p['settings']['chunking']}, embeddings `{p['settings']['embedding_model']}`. "
         f"{p['documents']} documents in `_metadata.csv`.", "",
         f"**Literal** (W2 loader on `week3/corpus`): indexes {p['literal']['top_level_files_indexed']} "
         f"(the export's own note, not a corpus document) and **0 of {p['documents']}** documents.",
         f"**Recursive** (W2 loader, every .md/.txt): **{p['totals']['recursive_loaded']} of {p['documents']}** "
         f"loaded, {p['totals']['recursive_chars']:,} chars, {p['totals']['recursive_chunks']} chunks.",
         f"**Full** (reference extractor, all formats): {p['totals']['full_chars']:,} chars.", ""]
    for key, title in (("by_source_system", "Source system"), ("by_format", "Format")):
        L += [f"| {title} | Documents | Loaded, literal | Loaded, recursive | W2 chunks | Chars (full extract) |",
              "|---|---:|---:|---:|---:|---:|"]
        for k, v in p[key].items():
            L.append(f"| {k} | {v['total']} | {v.get('literal_loaded', 0)} | {v.get('recursive_loaded', 0)} | "
                     f"{v.get('w2_chunks', 0)} | {v.get('full_chars', 0):,} |")
        L.append("")
    L.append("Languages (langdetect, per document): " + ", ".join(f"{k} {v}" for k, v in p["languages"].items()))
    if "embedding" in p:
        e = p["embedding"]
        L += ["", f"## Index builds (measured, {e['device']}; model load {e['model_load_s']} s not included)", "",
              "| View | Files | Chunks | Chars | Embedding tokens (cl100k) | Build wall clock | Index on disk | "
              f"Cost @ ${p['settings']['price_per_1m_tokens']}/1M |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for b in e["builds"]:
            L.append(f"| {b['view']} | {b['files']} | {b['chunks']} | {b['chars']:,} | {b['embedding_tokens']:,} | "
                     f"{b['index_build_s']} s | {b['index_bytes'] / 1024:,.0f} KiB | ${b['cost_usd_at_price']:.6f} |")
    q = p.get("quality_evidence", {})
    if q:
        L += ["", "## Data-quality evidence", "", "```json", json.dumps(q, indent=1, ensure_ascii=False)[:12000], "```"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
