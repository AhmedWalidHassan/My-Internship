"""
Duplicate detection (Week 3 Task 3). Three kinds, three policies, measured in
week3/task_03_ingestion/evidence/dedup_report.json:

1. Repeated sentences WITHIN a document (the R3 manual repeats ~10 safety sentences 80+ times):
   REMOVED at parse time, first occurrence kept (normalize.drop_repeated_sentences).
2. Exact duplicate chunks ACROSS documents (same body text): keep the most authoritative, label
   the others. (None in this corpus, but checked on every ingest.)
3. Near-duplicate DOCUMENTS from DIFFERENT source systems: a copy or mirror of a document from a
   more authoritative source. Found by containment (share of the smaller document's word
   3-shingles that appear in the other) >= CONTAIN, or declared ("This page mirrors IT-STD-003
   v2.0"). KEPT and LABELLED: every chunk of the copy gets `duplicate_of` = the authoritative
   document. Which one to show is a ranking decision for Tasks 4/5. Deleting the copy here would
   make one document's index content depend on another's and break per-document incremental ingest.

NOT duplicates, by decision: documents from the SAME source that share a template (team wiki pages
up to 0.79 containment, monthly newsletters up to 0.80, meeting notes up to 0.74). They share filler,
not facts ("Karim is on PTO next week" vs "Sofia is on PTO next week"), so merging them would lose
information.

Labelling runs over the stored chunk texts on every ingest, with no embedding, so it stays correct
when only one file changed.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

CONTAIN = 0.75
# Most authoritative first (Task 5 refines this with versions and effective dates).
AUTHORITY = ["policy-portal", "drive", "wiki", "intranet", "intranet-legacy", "scanned-archive"]


def body(text: str) -> str:
    """The chunk without its first line (the context header every chunk starts with)."""
    return text.split("\n", 1)[1] if "\n" in text else text


def shingles(text: str, k: int = 3) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i:i + k]) for i in range(max(len(words) - k + 1, 1))} if words else set()


def authority(meta: dict) -> float:
    s = meta.get("source_system", "")
    rank = AUTHORITY.index(s) if s in AUTHORITY else len(AUTHORITY)
    if str(meta.get("status", "")).lower() == "draft":
        rank += 0.5                                             # a draft never outranks the approved text
    return rank


def find_duplicates(chunks: list) -> dict:
    """{"exact_chunks": [...], "near_documents": [...]} over chunks of an export (metadata path,
    source_system, mirrors)."""
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[c.metadata.get("path", c.metadata.get("source"))].append(c)

    exact, seen = [], {}
    for path, cs in by_doc.items():
        for c in cs:
            n = re.sub(r"\s+", " ", body(c.page_content).lower()).strip()
            if len(n) < 60:
                continue
            h = hashlib.sha1(n.encode()).hexdigest()
            if h in seen and seen[h][0] != path:
                exact.append({"a": seen[h][1], "b": c})
            seen.setdefault(h, (path, c))

    docs = {p: {"meta": cs[0].metadata, "sh": shingles(" ".join(body(c.page_content) for c in cs))}
            for p, cs in by_doc.items()}
    ids = {}
    for p, d in docs.items():
        if d["meta"].get("doc_id"):
            ids.setdefault(d["meta"]["doc_id"], []).append(p)
    near = []
    paths = sorted(docs)
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            ma, mb = docs[a]["meta"], docs[b]["meta"]
            if ma.get("source_system") == mb.get("source_system"):
                continue                                         # templated siblings: not duplicates
            sa, sb = docs[a]["sh"], docs[b]["sh"]
            if not sa or not sb:
                continue
            small, big = (a, b) if len(sa) <= len(sb) else (b, a)
            contain = len(sa & sb) / min(len(sa), len(sb))
            declared = any(str(m.get("mirrors", "")).split(" ")[0] and big in ids.get(str(m["mirrors"]).split(" ")[0], [])
                           for m in (docs[small]["meta"],))
            if contain >= CONTAIN or declared:
                near.append({"copy": small, "of": big, "containment": round(contain, 3), "declared": declared})
    return {"exact_chunks": exact, "near_documents": near}


def label(chunks: list, found: dict) -> int:
    """Set duplicate_of / duplicate_kind on the less authoritative side. Clears stale labels
    first, so a fixed copy loses its label. Returns how many chunks carry a label."""
    for c in chunks:
        c.metadata.pop("duplicate_of", None)
        c.metadata.pop("duplicate_kind", None)
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[c.metadata.get("path")].append(c)
    for pair in found["near_documents"]:
        a, b = pair["copy"], pair["of"]
        ma, mb = by_doc[a][0].metadata, by_doc[b][0].metadata
        copy, orig = (a, b) if authority(ma) >= authority(mb) else (b, a)
        for c in by_doc[copy]:
            c.metadata["duplicate_of"] = orig
            c.metadata["duplicate_kind"] = "mirror" if pair["declared"] else "near-copy"
    for pair in found["exact_chunks"]:
        a, b = pair["a"], pair["b"]
        keep, dup = (a, b) if authority(a.metadata) <= authority(b.metadata) else (b, a)
        dup.metadata.setdefault("duplicate_of", f"{keep.metadata.get('path')}#{keep.metadata.get('chunk')}")
        dup.metadata.setdefault("duplicate_kind", "exact")
    return sum(1 for c in chunks if "duplicate_of" in c.metadata)
