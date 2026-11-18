"""
From a corpus file to indexable chunks.

    rows = read_metadata(corpus)                         # _metadata.csv, by path
    chunks, report = build_chunks(path, rel, rows[rel], chunk_size, chunk_overlap)

A chunk is one or more whole sections packed up to `chunk_size` characters (a longer section is
split with overlap), or ONE spreadsheet/CSV row. Every chunk starts with a context line,
"<title> [<id> v<version> · <status> · effective <date>] › <section>", so a passage still says
which document and version it came from once it is cut out of it. Metadata on every chunk:
`_metadata.csv` (path, title, owner_team, acl_groups, last_modified, source_system) plus what was
parsed from the document text (doc_id, version, status, effective_date, supersedes, content_date,
marking, mirrors, proposed_effective_date) and the chunk's language.

`last_modified` is copied for completeness but NOT used as a version date: for intranet-legacy it
is the 2026-01-15 migration date and for the scans the 2023 scan date (Task 1 issue #8).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from langchain_core.documents import Document

from ingest.loaders import Parsed, load
from ingest.normalize import language

LOADER_VERSION = "w3-loaders-1"
EXPORT_EXT = (".md", ".txt", ".pdf", ".html", ".xlsx", ".csv")
META_FIELDS = ("doc_id", "version", "status", "effective_date", "supersedes", "content_date", "marking",
               "mirrors", "proposed_effective_date", "owner", "edited_by")


def read_metadata(data_dir: Path) -> dict[str, dict]:
    with open(Path(data_dir) / "_metadata.csv", encoding="utf-8") as f:
        return {r["path"]: r for r in csv.DictReader(f)}


def corpus_snapshot(data_dir: Path) -> str | None:
    """The export's snapshot date, from its cover note ("snapshot 2026-10-01"), else the newest
    last_modified in _metadata.csv."""
    readme = Path(data_dir) / "README.md"
    if readme.exists():
        m = re.search(r"snapshot (\d{4}-\d{2}-\d{2})", readme.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    try:
        return max(r["last_modified"] for r in read_metadata(data_dir).values())
    except Exception:
        return None


def _context(p: Parsed) -> str:
    m = p.meta
    tags = []
    if m.get("doc_id"):
        tags.append(m["doc_id"] + (f" v{m['version']}" if m.get("version") else ""))
    elif m.get("version"):
        tags.append(m["version"] if not m["version"][0].isdigit() else f"v{m['version']}")
    if m.get("status"):
        tags.append({"draft": "DRAFT, not approved"}.get(m["status"].lower(), m["status"]))
    if m.get("effective_date"):
        tags.append(f"effective {m['effective_date']}")
    elif m.get("content_date"):
        tags.append(m["content_date"])
    return p.title + (f" [{' · '.join(tags)}]" if tags else "")


def _split(text: str, size: int, overlap: int) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap).split_text(text)


def build_chunks(path: Path, rel: str, row: dict, chunk_size: int, chunk_overlap: int) -> tuple[list[Document], dict]:
    parsed = load(Path(path), row.get("source_system", ""))
    context = _context(parsed)
    budget = max(chunk_size - len(context) - 40, 200)
    pieces: list[tuple[str, str]] = []                    # (section label, body)
    pack_heads, pack = [], []

    def flush():
        if pack:
            pieces.append(("; ".join(h for h in pack_heads if h), "\n".join(pack)))
        pack_heads.clear()
        pack.clear()

    for sec in parsed.sections:
        if sec.records:
            flush()
            pieces.extend((sec.heading, rec) for rec in sec.paragraphs)
            continue
        body = "\n".join(sec.paragraphs)
        block = (f"{sec.heading}\n{body}" if sec.heading else body)
        if len(block) > budget:
            flush()
            for part in _split(body, budget, chunk_overlap):
                pieces.append((sec.heading, part))
            continue
        if sum(len(x) + 1 for x in pack) + len(block) > budget:
            flush()
        pack_heads.append(sec.heading)
        pack.append(block)
    flush()

    base = {"source": Path(rel).name, "path": rel, "title": parsed.title, "format": Path(rel).suffix.lstrip("."),
            "source_system": row.get("source_system", ""), "acl_groups": row.get("acl_groups", "all"),
            "owner_team": row.get("owner_team", ""), "last_modified": row.get("last_modified", ""),
            **{k: v for k, v in parsed.meta.items() if k in META_FIELDS and v}}
    docs = []
    for i, (section, body) in enumerate(pieces):
        text = f"{context}{' › ' + section if section else ''}\n{body}"
        docs.append(Document(page_content=text,
                             metadata={**base, "section": section, "chunk": i, "language": language(body)}))
    report = {"path": rel, "format": base["format"], "source_system": base["source_system"], "status": "loaded",
              "title": parsed.title, "chunks": len(docs), "chars": len(parsed.text()),
              "language": language(parsed.text()),
              "parsed": {k: v for k, v in parsed.meta.items() if v}, "notes": parsed.notes}
    if not docs:
        report.update(status="skipped", reason="no text after parsing")
    return docs, report
