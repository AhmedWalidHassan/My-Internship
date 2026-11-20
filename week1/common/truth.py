"""
Week 3 Task 5 — time and truth: which retrieved passage states the CURRENT, APPROVED rule.

Decided at retrieval time, from metadata, with no LLM call (`curate()` runs inside the graph's
`retrieve` node):

1. Versions. Passages that carry a `doc_id` (parsed from the policy header block in Task 3) are
   compared with every other version of that document in the index (`Catalog`). As of `AS_OF_DATE`,
   the CURRENT version is the approved one with the latest effective date that isn't in the future.
   A superseded version is dropped, and if it was retrieved without the current one, the current one is
   fetched from the catalog instead. A version that isn't in force yet is kept, labelled NOT YET IN
   EFFECT, so the answer can mention an upcoming change.
2. Drafts are labelled DRAFT (a proposal, not policy) and placed last.
3. Sources without versions are ranked by the authority order below. Legacy intranet copies and
   scans that cover the same topic as a current policy passage are dropped (they are superseded
   copies). Lower-authority pages (wiki, newsletter, meeting note) on the same topic are kept but
   labelled, so the answer can say "the wiki still says X".
4. Ambiguity: when the question says "the rover" without naming the R2 or the R3 and the passages
   cover both, a note tells the generator to answer for each (never to pick one silently).

Every surviving passage gets a `truth_label` (shown to the generator next to the passage) and a
`truth_status`. Placing the decision here rather than at ingestion keeps the time-travel test
possible (AS_OF_DATE is read per query); placing it before generation means the model never has to
work out dates itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from langchain_core.documents import Document

# Source authority, highest first: (rank, name, path prefixes / source systems, justification)
AUTHORITY = [
    (1, "approved policy", ("policies/",),
     "the policy portal is the controlled, versioned system of record: every document has an ID, a "
     "version, an effective date and an approval status"),
    (2, "product and owner documentation", ("product/", "hr_restricted/"),
     "written and maintained by the owning team for the thing it describes (data sheets, manuals, SLA, "
     "parts, HR guidance), but not versioned by the policy process"),
    (3, "wiki", ("wiki/", "cairo/"),
     "maintained, but unversioned and edited by anyone: pages lag behind policy changes (VPN Setup "
     "Guide, Benefits Overview, Sales IT tips) and some only mirror a policy"),
    (4, "newsletter", ("newsletters/",),
     "dated announcements that summarise a change once; accurate on the day, never updated"),
    (5, "meeting note", ("meetings/",),
     "informal notes that mention rules in passing, without authority or follow-up"),
    (6, "legacy and archive", ("legacy_intranet/", "scanned_archive/"),
     "the 2024 intranet migrated as-is and OCR scans from 2016–2019: superseded wherever the policy "
     "portal covers the topic"),
]
STOP = set("the a an and or of to in on for is are be by with from as at it its this that any all "
           "per may must can not no you your our their they we i do does what how when which who".split())
SAME_TOPIC = 0.18                       # content-word Jaccard: "these passages are about the same rule"


def authority(meta: dict) -> tuple[int, str]:
    path = meta.get("path", "")
    for rank, name, prefixes, _ in AUTHORITY:
        if path.startswith(prefixes):
            return rank, name
    return 2, "document"                # a plain-folder corpus (Week 1): no authority information


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$%][a-z0-9$%.,-]*[a-z0-9%]|[a-z0-9]", text.lower())
            if w not in STOP and len(w) > 2}


def jaccard(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def _date(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


@dataclass
class Version:
    doc_id: str
    version: str
    status: str
    effective: date | None
    path: str
    chunks: list


class Catalog:
    """Every version of every document with a doc_id, built from the index's chunks."""

    def __init__(self, docs):
        self.by_id: dict[str, dict[str, Version]] = {}
        for d in docs:
            m = d.metadata
            if not m.get("doc_id"):
                continue
            v = self.by_id.setdefault(m["doc_id"], {}).setdefault(m.get("path", m.get("source", "")), Version(
                m["doc_id"], str(m.get("version", "")), str(m.get("status", "")).lower(),
                _date(m.get("effective_date")), m.get("path", m.get("source", "")), []))
            v.chunks.append(d)

    def current(self, doc_id: str, as_of: date) -> Version | None:
        """The approved version with the latest effective date on or before `as_of`."""
        live = [v for v in self.by_id.get(doc_id, {}).values()
                if v.status == "approved" and v.effective and v.effective <= as_of]
        return max(live, key=lambda v: v.effective) if live else None


def classify(d: Document, catalog: Catalog, as_of: date) -> tuple[str, str]:
    """(status, label) for one passage, as of `as_of`."""
    m = d.metadata
    rank, kind = authority(m)
    title = m.get("title", "") or m.get("source", "")
    if str(m.get("status", "")).lower() == "draft":
        return "DRAFT", (f"{m.get('doc_id', title)} v{m.get('version', '?')}: DRAFT, a proposal that is NOT approved "
                         "policy (never state it as a rule)")
    if m.get("doc_id") and _date(m.get("effective_date")):
        eff = _date(m["effective_date"])
        ident = f"{m['doc_id']} v{m.get('version', '?')}"
        cur = catalog.current(m["doc_id"], as_of)
        if eff > as_of:
            then = f"; {cur.doc_id} v{cur.version} applies until then" if cur else ""
            return "NOT_YET_IN_EFFECT", f"{ident}: NOT YET IN EFFECT on {as_of} (takes effect {eff}){then}"
        if cur is not None and cur.path != m.get("path"):
            return "SUPERSEDED", f"{ident}: SUPERSEDED by v{cur.version}, effective {cur.effective}"
        return "CURRENT", f"{ident}, effective {eff}: CURRENT approved version as of {as_of}"
    if rank <= 2:
        return "AUTHORITATIVE", f"{title} ({kind})"
    if rank == 6:
        what = "legacy intranet copy from 2024" if m.get("path", "").startswith("legacy_") else "scanned archive"
        return "OUTDATED", f"{title}: {what}, OUTDATED (superseded wherever the policy portal covers the topic)"
    when = m.get("content_date") or m.get("last_modified") or "?"
    return "LOWER_AUTHORITY", (f"{title}: {kind} ({when}), lower authority than the policy portal and may be "
                               "out of date")


def curate(docs: list[Document], question: str, catalog: Catalog, as_of: date) -> tuple[list[Document], list[str]]:
    """The passages the generator should see, labelled and ordered; plus notes on what was changed."""
    notes: list[str] = []
    out: list[Document] = []
    seen_paths = {d.metadata.get("path") for d in docs}

    def labelled(d, status, label):
        return Document(page_content=d.page_content, id=getattr(d, "id", None),
                        metadata={**d.metadata, "truth_status": status, "truth_label": label})

    for d in docs:
        out.append(labelled(d, *classify(d, catalog, as_of)))

    # 1. superseded versions: bring in the current version if it wasn't retrieved, then drop them
    for d in [x for x in out if x.metadata["truth_status"] in ("SUPERSEDED", "NOT_YET_IN_EFFECT")]:
        cur = catalog.current(d.metadata["doc_id"], as_of)
        if cur and cur.path not in seen_paths:
            best = sorted(cur.chunks, key=lambda c: jaccard(question + " " + d.page_content, c.page_content),
                          reverse=True)[:2]
            out += [labelled(c, *classify(c, catalog, as_of)) for c in best]
            seen_paths.add(cur.path)
            notes.append(f"added {cur.doc_id} v{cur.version} (current) for retrieved {d.metadata['path']}")
    # 1b. a draft of a document we are answering from, when the question is about what the draft
    # changes ("Is Northwind switching to flexible time off?"): words the draft uses and the current
    # version doesn't. Labelled DRAFT, so it can only be mentioned as a proposal.
    q_words = _words(question)
    for doc_id in {x.metadata.get("doc_id") for x in out if x.metadata["truth_status"] == "CURRENT"} - {None}:
        versions = catalog.by_id.get(doc_id, {}).values()
        current_words = set().union(*(_words(c.page_content) for v in versions if v.status == "approved"
                                      for c in v.chunks)) if versions else set()
        for v in versions:
            if v.status != "draft" or v.path in seen_paths:
                continue
            specific = set().union(*(_words(c.page_content) for c in v.chunks)) - current_words
            if q_words & specific:
                best = max(v.chunks, key=lambda c: jaccard(question, c.page_content))
                out.append(labelled(best, *classify(best, catalog, as_of)))
                seen_paths.add(v.path)
                notes.append(f"added draft {v.doc_id} v{v.version} (the question uses its terms: "
                             f"{sorted(q_words & specific)[:4]})")
    dropped = [x for x in out if x.metadata["truth_status"] == "SUPERSEDED"]
    out = [x for x in out if x.metadata["truth_status"] != "SUPERSEDED"]
    notes += [f"dropped superseded {x.metadata['path']}" for x in dropped]

    # 2. same-topic copies of a current/authoritative passage: drop legacy and scans, flag the rest
    anchors = [x for x in out if x.metadata["truth_status"] in ("CURRENT", "AUTHORITATIVE")]
    kept = []
    for x in out:
        if x.metadata["truth_status"] in ("OUTDATED", "LOWER_AUTHORITY") and anchors:
            best = max(anchors, key=lambda a: jaccard(x.page_content, a.page_content))
            if jaccard(x.page_content, best.page_content) >= SAME_TOPIC:
                ref = best.metadata.get("doc_id") or best.metadata.get("title")
                if x.metadata["truth_status"] == "OUTDATED":
                    notes.append(f"dropped outdated {x.metadata['path']} (same topic as {ref})")
                    continue
                x.metadata["truth_label"] += (f"; covers the same topic as {ref}: where they differ, {ref} "
                                              "applies and this page is out of date")
        kept.append(x)
    out = kept

    # 3. order: authority, then drafts and not-yet-effective versions last; stable within a level
    out.sort(key=_order)
    return out, notes


RESTORE = 0.07   # weaker than SAME_TOPIC: a conflicting page rewords the policy (Sales IT tips vs IT-STD-003: 0.085)


def _order(x: Document) -> float:
    s = x.metadata.get("truth_status", "")
    return (authority(x.metadata)[0] + (6 if s in ("DRAFT", "NOT_YET_IN_EFFECT") else 0)
            + (0.5 if s == "OUTDATED" else 0))


def restore_anchors(kept: list[Document], candidates: list[Document]) -> tuple[list[Document], list[str]]:
    """After the relevance grader: if it kept a lower-authority or outdated passage but dropped the
    current policy on the same topic, put the policy back (at most one per kept passage). Otherwise a
    question phrased about the wiki ("the sales IT tips say ...") is answered from the wiki alone."""
    ids = {id(x) for x in kept}
    dropped = [c for c in candidates if id(c) not in ids
               and c.metadata.get("truth_status") in ("CURRENT", "AUTHORITATIVE")]
    notes, out = [], list(kept)
    for x in kept:
        if x.metadata.get("truth_status") not in ("LOWER_AUTHORITY", "OUTDATED") or not dropped:
            continue
        best = max(dropped, key=lambda c: jaccard(x.page_content, c.page_content))
        if jaccard(x.page_content, best.page_content) >= RESTORE and id(best) not in {id(o) for o in out}:
            out.append(best)
            notes.append(f"restored {best.metadata.get('path')} (dropped by the grader; outranks the kept "
                         f"{x.metadata.get('path')})")
    out.sort(key=_order)
    return out, notes


_ROVER = re.compile(r"\b(rover|robot|amr)s?\b", re.I)
_MODEL = re.compile(r"\bR[23]\b")


def ambiguity_note(question: str, docs: list[Document]) -> str | None:
    """'The rover' with no model named, when the passages describe both: answer for each reading.
    (Policy: answer every reading rather than ask back; see week3/RESULTS.md, Task 5.)"""
    if not _ROVER.search(question) or _MODEL.search(question):
        return None
    text = " ".join(d.metadata.get("path", "") + " " + d.metadata.get("title", "") + " " + d.page_content[:400]
                    for d in docs)
    if re.search(r"\bR2\b", text) and re.search(r"\bR3\b", text):
        return ("NOTE: the question says 'the rover' but does not say whether it means the R2 or the R3, and "
                "the documents differ for the two. Answer for BOTH, labelled 'R2:' and 'R3:'. Do not pick one.")
    return None


def source(d: Document) -> dict:
    """The structured citation for a passage (ChatResponse.sources)."""
    m = d.metadata
    return {"path": m.get("path") or m.get("source", "unknown"), "title": m.get("title") or None,
            "doc_id": m.get("doc_id") or None, "version": (str(m["version"]) if m.get("version") else None),
            "effective_date": m.get("effective_date") or None, "section": m.get("section") or None,
            "status": m.get("truth_status") or (m.get("status") or None)}


def cited_label(s: dict) -> str:
    """'HR-POL-004 v3.0' for a versioned document, else its path (for the request log line)."""
    if s.get("doc_id"):
        return f"{s['doc_id']} v{s['version']}" if s.get("version") else s["doc_id"]
    return s["path"]
