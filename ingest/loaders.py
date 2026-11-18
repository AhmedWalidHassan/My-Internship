"""
One loader per format. Each returns a `Parsed` document: a title, sections of paragraphs (or of
self-contained records, for spreadsheet rows), the metadata it could read from the text, and notes
on what it removed. Why each format looks the way it does is in week3/task_03_ingestion/LOADERS.md.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from ingest.normalize import clean, drop_repeated_sentences, repair_ocr

MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
MON3 = {m[:3]: i for m, i in MONTHS.items()}


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    records: bool = False            # True: every paragraph is a self-contained row (one chunk each)


@dataclass
class Parsed:
    title: str
    sections: list[Section]
    meta: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)

    def text(self) -> str:
        return "\n".join(p for s in self.sections for p in s.paragraphs)


def _month_date(text: str) -> str | None:
    """'May 2026' -> '2026-05'; 'Jan 1 2017' -> '2017-01-01'."""
    m = re.search(r"\b([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),?\s+(\d{4})\b", text)
    if m and m.group(1).lower()[:3] in MON3:
        return f"{m.group(3)}-{MON3[m.group(1).lower()[:3]]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b([A-Z][a-z]{2,8})\s+(\d{4})\b", text)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"
    return None


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
META_KEYS = {"document id": "doc_id", "version": "version", "status": "status", "effective date": "effective_date",
             "owner": "owner", "supersedes": "supersedes"}
MARKING = re.compile(r"\b(CONFIDENTIAL|RESTRICTED|INTERNAL)\b")
PAGE_NO = re.compile(r"\s*[-–|]?\s*Page \d+ of \d+\s*$")


def _merge_rows(rows: list[list[str]]) -> list[list[str]]:
    """Text extraction splits a wrapped cell into extra rows. A row continues the previous one when
    its first cell is empty, starts with '(' , or is a lower-case word with nothing else in the row,
    or when the previous first cell ends with '-' (an identifier broken at its hyphen)."""
    out = []
    for row in rows:
        if out:
            prev = out[-1]
            rest_empty = all(not c for c in row[1:])
            if (not row[0] or row[0].startswith("(") or (rest_empty and row[0][:1].islower())
                    or (rest_empty and prev[0].endswith("-"))):
                for i, c in enumerate(row):
                    if c:
                        prev[i] = (prev[i] + c) if prev[i].endswith("-") else f"{prev[i]} {c}".strip()
                continue
        out.append(list(row))
    return out


def _table(page, table, meta: dict) -> list[str]:
    """A PDF table as lines of 'Header: value | Header: value' (rows keep their column names), or
    'Key: value' for a two-column key/value table. A leading metadata block (Document ID, Version,
    Status, Effective date, Owner, Supersedes) goes into `meta` instead of the text."""
    import pymupdf

    raw = [[re.sub(r"\s+", " ", clean(page.get_text("text", clip=pymupdf.Rect(c)))) if c else "" for c in r.cells]
           for r in table.rows]
    rows = _merge_rows(raw)
    body = []
    for row in rows:
        key = row[0]
        m = re.match(r"(Document ID)\s+(\S+-)$", key)            # "Document ID IT-" | "STD-001"
        if m:
            key, row = m.group(1), [m.group(1), m.group(2) + row[1]] + row[2:]
        k = re.sub(r"\s+", " ", key).strip().lower()
        if k in META_KEYS and not body:
            meta[META_KEYS[k]] = " ".join(c for c in row[1:] if c).strip()
            continue
        body.append(row)
    if not body:
        return []
    ncol = max(len(r) for r in body)
    header = body[0] if (ncol >= 2 and all(body[0]) and not any(re.search(r"\d", c) for c in body[0])) else None
    lines = []
    for row in (body[1:] if header else body):
        if header:
            cells = [f"{h}: {v}" for h, v in zip(header, row) if v]
        else:
            cells = [f"{row[0]}: {' '.join(c for c in row[1:] if c)}".strip(": ")]
        if cells:
            lines.append(" | ".join(cells))
    return lines


_HEADER_KEYS = re.compile(r"\b(Document ID|Version|Status|Effective\s+date|Owner|Supersedes)\b")


def _text_metadata(sections: list[Section], meta: dict) -> None:
    """The policy header block ("Document ID", "Version", ... "Supersedes") when PyMuPDF did not
    detect it as a table: the leading short lines of the first section (one paragraph per line,
    or all in one block), split on the known keys, then removed from the text."""
    if not sections or not sections[0].paragraphs or not sections[0].paragraphs[0].startswith("Document ID"):
        return
    paras = sections[0].paragraphs
    n = 0
    while n < len(paras) and (len(paras[n]) < 80 or _HEADER_KEYS.match(paras[n])) and not paras[n].endswith("."):
        n += 1
    parts = _HEADER_KEYS.split(" ".join(paras[:n]))
    for key, value in zip(parts[1::2], parts[2::2]):
        k = re.sub(r"\s+", " ", key).lower()
        if value.strip():
            meta[META_KEYS[k]] = re.sub(r"\s*-\s+(?=[A-Z0-9]{2,}-?\d)", "-", value.strip())   # "IT- STD-009"
    sections[0].paragraphs = paras[n:]


def _side_by_side(blocks: list) -> bool:
    rows = {}
    for b in blocks:
        for ln in b["lines"]:
            if "".join(s["text"] for s in ln["spans"]).strip():
                rows.setdefault(round(ln["bbox"][1] / 3), []).append(ln["bbox"][0])
    return any(len(xs) >= 2 and max(xs) - min(xs) > 40 for xs in rows.values())


def load_pdf(path: Path) -> Parsed:
    import pymupdf

    meta, notes, markings = {}, {"furniture_lines_removed": 0}, []
    title, sections = None, [Section("")]
    with pymupdf.open(path) as doc:
        notes["pages"] = len(doc)
        for page in doc:
            blocks = [b for b in page.get_text("dict")["blocks"] if b.get("lines")]
            # Table detection is the slow part (~0.16 s a page, these tables have no ruling lines), so
            # it only runs on pages with text side by side: a table or the policy header block.
            tables = page.find_tables().tables if _side_by_side(blocks) else []
            boxes = [pymupdf.Rect(t.bbox) for t in tables]
            emitted = set()
            for b in sorted(blocks, key=lambda b: (round(b["bbox"][1]), b["bbox"][0])):
                rect = pymupdf.Rect(b["bbox"])
                inside = next((i for i, tb in enumerate(boxes)
                               if (rect & tb).get_area() > 0.5 * max(rect.get_area(), 1e-6)), None)
                if inside is not None:
                    if inside not in emitted:
                        emitted.add(inside)
                        lines = _table(page, tables[inside], meta)
                        if lines:
                            sections[-1].paragraphs.append("\n".join(lines))
                    continue
                spans = [s for ln in b["lines"] for s in ln["spans"] if s["text"].strip()]
                if not spans:
                    continue
                size = max(s["size"] for s in spans)
                parts = []
                for ln in b["lines"]:
                    t = "".join(s["text"] for s in ln["spans"]).strip()
                    if t:
                        parts.append(t)
                text = ""
                for t in parts:                                    # "Part-" + "time" -> "Part-time"
                    text = (text + t) if text.endswith("-") else f"{text} {t}".strip()
                text = clean(text)
                if size <= 8:                                     # page furniture (7 pt header/footer)
                    notes["furniture_lines_removed"] += 1
                    rest = PAGE_NO.sub("", text).strip(" -|")
                    mk = MARKING.search(rest)
                    if mk:                                # "CONFIDENTIAL - for licensed operators only ..."
                        label = mk.group(1) if rest.startswith("Northwind Robotics") else rest
                        if label not in markings:
                            markings.append(label)
                    elif rest and not rest.startswith("Northwind Robotics") and len(rest.split()) >= 3:
                        sections[-1].paragraphs.append(rest)      # real information in a footer
                    continue
                if size >= 15.5 and title is None:
                    title = text
                elif size >= 14:
                    sections.append(Section(text))
                elif sections[-1].paragraphs and text[:1].islower():
                    sections[-1].paragraphs[-1] += " " + text     # a sentence continued across a page break
                else:
                    sections[-1].paragraphs.append(text)
    if "doc_id" not in meta and sections:
        _text_metadata(sections, meta)                           # header block not drawn as a table
    if markings:
        meta["marking"] = "; ".join(markings)
    m = re.search(r"Revision ([A-Z0-9]+),\s*([A-Z][a-z]+ \d{4})", "\n".join(sections[0].paragraphs) if sections else "")
    if m:
        meta.setdefault("version", f"Rev {m.group(1)}")
        meta["content_date"] = _month_date(m.group(2))
    sections = [s for s in sections if s.paragraphs]
    notes["sentences_repeated_dropped"] = 0
    if sum(len(p) for s in sections for p in s.paragraphs) > 20000:       # long documents only (the manual)
        seen = set()
        for s in sections:
            s.paragraphs, n = drop_repeated_sentences(s.paragraphs, seen)
            notes["sentences_repeated_dropped"] += n
        sections = [s for s in sections if s.paragraphs]
    return Parsed(title or path.stem, sections, meta, notes)


# ---------------------------------------------------------------------------
# HTML (wiki pages and newsletters)
# ---------------------------------------------------------------------------
CHROME = [".nav", ".sidebar", ".footer", ".unsub", "script", "style", "header", "nav", "footer"]


def load_html(path: Path) -> Parsed:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    meta, notes = {}, {}
    full = len(soup.get_text(" ", strip=True))
    footer = soup.select_one(".footer")
    if footer:
        m = re.search(r"Last edited by (\S+) on (\d{4}-\d{2}-\d{2})", footer.get_text(" ", strip=True))
        if m:
            meta["edited_by"], meta["content_date"] = m.group(1), m.group(2)
    issue = soup.select_one(".issue")
    if issue:
        meta["content_date"] = issue.get_text(strip=True)
        issue.decompose()
    for sel in CHROME:
        for el in soup.select(sel):
            el.decompose()
    root = soup.select_one(".content") or soup.body or soup
    title_el = root.find("h1") or soup.find("title")
    title = clean(title_el.get_text(" ", strip=True)).replace(" - Northwind Wiki", "") if title_el else path.stem
    if root.find("h1"):
        root.find("h1").decompose()
    sections = [Section("")]
    for el in root.find_all(["h2", "h3", "p", "li", "pre", "tr"]):
        if el.find_parent(["li", "p", "tr"]) is not None:
            continue
        text = re.sub(r"\s+", " ", clean(el.get_text(" ", strip=True)))
        if not text:
            continue
        if el.name in ("h2", "h3"):
            sections.append(Section(text))
        elif el.name == "li":
            sections[-1].paragraphs.append("- " + text)
        else:
            sections[-1].paragraphs.append(text)
    loose = [re.sub(r"\s+", " ", clean(t)) for t in root.find_all(string=True, recursive=False) if t.strip()]
    if loose:                                                   # text directly inside the content div
        sections[0].paragraphs = loose + sections[0].paragraphs
    m = re.search(r"mirrors ([A-Z]{2,4}-[A-Z]{2,4}-\d{3})(?: (v[\d.]+))?", " ".join(p for s in sections for p in s.paragraphs))
    if m:
        meta["mirrors"] = " ".join(x for x in m.groups() if x)
    sections = [s for s in sections if s.paragraphs]
    kept = sum(len(p) for s in sections for p in s.paragraphs)
    notes["chrome_share_removed"] = round(1 - kept / full, 3) if full else 0
    return Parsed(title, sections, meta, notes)


# ---------------------------------------------------------------------------
# Spreadsheets and CSV: every row keeps its column names
# ---------------------------------------------------------------------------
def _records(header: list[str], rows: list[list]) -> list[str]:
    out = []
    for row in rows:
        cells = [f"{h}: {clean(str(v))}" for h, v in zip(header, row) if v not in (None, "")]
        if cells:
            out.append(" | ".join(cells))
    return out


def load_xlsx(path: Path) -> Parsed:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sections, notes = [], {"rows": 0}
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True) if any(c not in (None, "") for c in r)]
        if not rows:
            continue
        header = [clean(str(c)) if c is not None else "" for c in rows[0]]
        if len(header) >= 2 and all(isinstance(c, str) and c for c in rows[0]):
            recs = _records(header, rows[1:])
            notes["rows"] += len(recs)
            sections.append(Section(ws.title, recs, records=True))
        else:                                                   # a "Read me" / "Notes" sheet: plain text
            sections.append(Section(ws.title, [clean(" ".join(str(c) for c in r if c is not None)) for r in rows]))
    meta = {}
    marks = [p for s in sections for p in s.paragraphs if MARKING.search(p) and not s.records]
    if marks:
        meta["marking"] = marks[0]
    return Parsed(path.stem.replace("_", " "), sections, meta, notes)


def load_csv(path: Path) -> Parsed:
    text = path.read_text(encoding="utf-8-sig")                 # strips the UTF-8 BOM (Task 1 issue #12)
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    header = [clean(c) for c in rows[0]]
    recs = _records(header, rows[1:])
    return Parsed(path.stem.replace("_", " "), [Section("", recs, records=True)], {}, {"rows": len(recs)})


# ---------------------------------------------------------------------------
# Markdown and plain text
# ---------------------------------------------------------------------------
def _md_table(lines: list[str]) -> list[str]:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    if len(rows) < 2:
        return [" | ".join(r) for r in rows]
    return _records(rows[0], rows[1:])


def load_markdown(path: Path) -> Parsed:
    text = clean(path.read_text(encoding="utf-8"))
    title, sections, meta = None, [Section("")], {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            sections[-1].paragraphs.extend(_md_table(block))
            continue
        if ln.startswith("# ") and title is None:
            title = ln[2:].strip()
        elif re.match(r"#{2,6} ", ln):
            sections.append(Section(ln.lstrip("#").strip()))
        elif ln.strip():
            para = re.sub(r"^\s*>\s?", "", ln).replace("**", "").strip()
            if sections[-1].paragraphs and not re.match(r"^(- |\d+\. )", para) and not lines[i - 1].strip() == "":
                sections[-1].paragraphs[-1] += " " + para
            else:
                sections[-1].paragraphs.append(para)
        i += 1
    title = (title or path.stem).replace("**", "")
    body = "\n".join(p for s in sections for p in s.paragraphs)
    if re.search(r"\bDRAFT\b", title + " " + body) and re.search(r"NOT APPROVED|for comment|proposal", body, re.I):
        meta["status"] = "draft"
    m = re.search(r"\b([A-Z]{2,4}-[A-Z]{2,4}-\d{3})\s+v(\d+(?:\.\d+)?)", title)
    if m:
        meta["doc_id"], meta["version"] = m.group(1), m.group(2)
    m = re.search(r"Fleet Manager (\d+\.\d+)", title)
    if m:
        meta["version"] = m.group(1)
    d = re.search(r"\(([A-Z][a-z]+ \d{4})\)", title)
    if d:
        meta["content_date"] = _month_date(d.group(1))
    for s in sections:
        if re.search(r"effective date", s.heading, re.I) and meta.get("status") == "draft":
            dm = re.search(r"\d{4}-\d{2}-\d{2}", " ".join(s.paragraphs))
            if dm:
                meta["proposed_effective_date"] = dm.group(0)
    mk = MARKING.search(title) or re.search(r"[A-Za-z -]*\bonly\b", title)   # "(RESTRICTED)", "(managers only)"
    if mk:
        meta["marking"] = mk.group(0).strip(" ()—")
    return Parsed(title, [s for s in sections if s.paragraphs], meta, {})


def load_text(path: Path, ocr: bool = False) -> Parsed:
    raw = clean(path.read_text(encoding="utf-8", errors="replace"))
    notes, meta = {}, {}
    if ocr:
        raw, notes["ocr_tokens_fixed"] = repair_ocr(raw)
    lines = [ln for ln in raw.splitlines()]
    title = lines[0].strip() if lines else path.stem
    sections, cur = [], Section("")
    for ln in lines[1:]:
        s = ln.strip()
        if not s:
            continue
        if re.fullmatch(r"[A-Z][A-Za-z ]+:", s):                    # "Notes:", "Action items:"
            if cur.paragraphs or cur.heading:
                sections.append(cur)
            cur = Section(s.rstrip(":"))
        elif s.startswith("- ") or not cur.paragraphs:
            cur.paragraphs.append(s)
        elif re.match(r"^(Date|Attendees|Q|A):", s):
            cur.paragraphs.append(s)
        else:
            cur.paragraphs[-1] += " " + s
    sections.append(cur)
    m = re.search(r"^Date:\s*(\d{4}-\d{2}-\d{2})", raw, re.M)
    if m:
        meta["content_date"] = m.group(1)
    m = re.search(r"Effective:\s*(.+)", raw)
    if m:
        meta["effective_date"] = _month_date(m.group(1))
    m = re.search(r"\brev(?:ision)?\.?\s+(\d{4})\b", raw, re.I)
    if m:
        meta["version"] = f"rev {m.group(1)}"
    if ocr and "content_date" not in meta:
        y = re.search(r"\b(19|20)\d{2}\b", raw)
        if y and "effective_date" not in meta:
            meta["content_date"] = y.group(0)
    if MARKING.search(title) or "managers only" in title.lower():
        meta["marking"] = title
    return Parsed(title, [s for s in sections if s.paragraphs], meta, notes)


def load(path: Path, source_system: str = "") -> Parsed:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return load_pdf(path)
    if ext == ".html":
        return load_html(path)
    if ext == ".xlsx":
        return load_xlsx(path)
    if ext == ".csv":
        return load_csv(path)
    if ext == ".md":
        return load_markdown(path)
    if ext == ".txt":
        return load_text(path, ocr=source_system == "scanned-archive")
    raise ValueError(f"no loader for {ext}")
