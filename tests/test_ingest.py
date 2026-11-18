"""
Fast tier — Week 3 Task 3 loaders, on real files of the corpus (read-only, offline).

One assertion per thing the brief asks a loader to get right: table rows rebuilt with their column
names, page furniture and wiki chrome removed, spreadsheet rows keeping their headers, Unicode
normalised (and Arabic unharmed), identifiers re-joined, OCR repaired, metadata parsed from the
text, and the manual's repeated boilerplate dropped without losing its needles.
"""

import unicodedata
from pathlib import Path

import pytest
from conftest import REPO_ROOT

from ingest import build_chunks, read_metadata
from ingest.loaders import load
from ingest.normalize import nfkc, repair_ocr

CORPUS = REPO_ROOT / "week3" / "corpus"


@pytest.fixture(scope="module")
def rows():
    return read_metadata(CORPUS)


def text_of(rel, rows):
    docs, report = build_chunks(CORPUS / rel, rel, rows[rel], 800, 100)
    return "\n".join(d.page_content for d in docs), docs, report


@pytest.mark.corpus
def test_pdf_table_rows_keep_their_columns_and_the_header_block_becomes_metadata(rows):
    text, docs, report = text_of("policies/finance/FIN-POL-002_travel_and_per_diem.pdf", rows)
    assert ("Tier: B | Countries: Egypt, India, Brazil, Mexico, Turkey, Vietnam | Meals per day: $55 | "
            "Hotel cap per night: $150") in text
    assert report["parsed"]["doc_id"] == "FIN-POL-002" and report["parsed"]["effective_date"] == "2026-01-15"
    assert "Page 1 of 1" not in text and "Controlled copy" not in text, "page furniture removed"
    assert "Document ID" not in text, "the header block is metadata, not text"
    assert docs[0].page_content.startswith("Travel & Per Diem Policy [FIN-POL-002 v4.0 · Approved · effective 2026-01-15]")


@pytest.mark.corpus
def test_pdf_metadata_ligatures_and_split_identifiers(rows):
    text, docs, report = text_of("policies/hr/HR-POL-004_PTO_v3.pdf", rows)
    assert "Completed years of service: 3 - 5 years | Annual PTO: 23 days" in text
    assert report["parsed"]["supersedes"] == "HR-POL-004 v2.0" and report["parsed"]["status"] == "Approved"
    assert "time off" in text.lower() and "ﬀ" not in text, "NFKC: 'Oﬀ' became 'Off'"
    _, docs9, report9 = text_of("policies/it/IT-STD-009_lost_or_stolen_devices.pdf", rows)
    assert report9["parsed"]["doc_id"] == "IT-STD-009", "'IT-\\nSTD-009' is re-joined"
    assert all(d.metadata["acl_groups"] == "all" and d.metadata["source_system"] == "policy-portal" for d in docs9)


def test_wrapped_table_cells_are_merged_back_into_their_rows():
    """The raw rows PyMuPDF returns for the corpus's tables (cells wrap into extra rows)."""
    from ingest.loaders import _merge_rows
    travel = [["Tier", "Countries", "Meals per", "Hotel cap per"], ["", "", "day", "night"],
              ["A", "United States, United Kingdom, Germany, Switzerland,", "$90", "$260"],
              ["", "Japan, Singapore", "", ""], ["B", "Egypt, India", "$55", "$150"]]
    assert _merge_rows(travel) == [["Tier", "Countries", "Meals per day", "Hotel cap per night"],
                                   ["A", "United States, United Kingdom, Germany, Switzerland, Japan, Singapore",
                                    "$90", "$260"], ["B", "Egypt, India", "$55", "$150"]]
    parts = [["NW-BMP-", "Ultrasonic bumper ring", "R3", "$520"], ["RING3", "", "", ""]]
    assert _merge_rows(parts) == [["NW-BMP-RING3", "Ultrasonic bumper ring", "R3", "$520"]]
    sla = [["Premium Plus", "24/7 with named engineer", "30 minutes", "24 hours, plus on-site technician"],
           ["(new in 2026)", "", "", "within 24 hours in supported metro"], ["", "", "", "areas"]]
    assert _merge_rows(sla) == [["Premium Plus (new in 2026)", "24/7 with named engineer", "30 minutes",
                                 "24 hours, plus on-site technician within 24 hours in supported metro areas"]]
    assert _merge_rows([["Ingress", "IP54 - indoor use only"], ["protection", ""]]) == [
        ["Ingress protection", "IP54 - indoor use only"]]


def test_synthetic_pdf_furniture_headings_ligatures_and_header_block(tmp_path):
    """A one-page PDF laid out like the policy portal's (7 pt furniture in the margins, 16 pt title,
    15 pt section headings, a header block), built in milliseconds."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 40), "Northwind Robotics Policy Portal | Controlled copy - printed copies are uncontrolled",
                     fontsize=7)
    page.insert_text((72, 90), "Lost or Stolen Devices", fontsize=16, fontname="hebo")
    y = 120
    for line in ["Document ID", "IT-", "STD-009", "Version", "1.0", "Status", "Approved", "Effective",
                 "date", "2025-10-01"]:
        page.insert_text((72, y), line, fontsize=10)
        y += 14
    page.insert_text((72, y + 20), "Reporting", fontsize=15, fontname="hebo")
    page.insert_text((72, y + 44), "Report it to Security within 1 hour of noticing; file an URGENT ticket.", fontsize=10)
    page.insert_text((72, 812), "Northwind Robotics - INTERNAL - Page 1 of 1", fontsize=7)
    pdf = tmp_path / "IT-STD-009.pdf"
    doc.save(pdf)

    parsed = load(pdf)
    text = parsed.text()
    assert parsed.title == "Lost or Stolen Devices" and [s.heading for s in parsed.sections] == ["Reporting"]
    assert parsed.meta["doc_id"] == "IT-STD-009" and parsed.meta["effective_date"] == "2025-10-01"
    assert parsed.meta["marking"] == "INTERNAL"
    assert "within 1 hour of noticing; file an URGENT ticket." in text
    assert nfkc("Paid Time Oﬀ, ﬁle, oﬃce, ﬂeet") == "Paid Time Off, file, office, fleet"   # the corpus's ligatures
    assert "Page 1 of 1" not in text and "Controlled copy" not in text and "Document ID" not in text


def test_manual_boilerplate_is_dropped_but_its_needles_survive(rows):
    text, docs, report = text_of("product/R3/R3_Operator_Manual_RevC.pdf", rows)
    assert report["notes"]["sentences_repeated_dropped"] > 1000
    assert text.count("Operators must complete the Northwind certified operator course") == 1
    assert "press and hold the blue RESUME button for 3 seconds" in text
    assert "The maximum ramp incline is 5 degrees when loaded and 8 degrees when unloaded." in text
    assert "Page 7 of 23" not in text and "CONFIDENTIAL" not in text
    assert report["parsed"]["marking"].startswith("CONFIDENTIAL"), "the marking is kept as metadata"
    assert len(docs) < 15, "23 pages collapse to a handful of chunks"


def test_wiki_chrome_is_dropped_and_the_edit_date_and_mirror_are_metadata(rows):
    text, docs, report = text_of("wiki/it/Password_Policy.html", rows)
    for chrome in ("Search the wiki", "Recently updated", "Was this page helpful", "Powered by Northwind Wiki"):
        assert chrome not in text
    assert "at least 16 characters" in text
    assert report["parsed"]["content_date"] == "2026-02-03" and report["parsed"]["mirrors"] == "IT-STD-003 v2.0"


def test_spreadsheet_rows_keep_their_headers_one_row_per_chunk(rows):
    _, docs, _ = text_of("product/Rover_Error_Codes_2026.xlsx", rows)
    e217 = [d for d in docs if "Code: E-217 |" in d.page_content]
    assert len(e217) == 1
    assert "Description: Left drive motor overcurrent" in e217[0].page_content
    assert "replace motor controller NW-MC-2210" in e217[0].page_content


def test_csv_bom_is_gone_and_arabic_survives_normalisation(rows):
    raw = (CORPUS / "cairo" / "الإجازات_الرسمية_2026.csv").read_text(encoding="utf-8")
    text, docs, _ = text_of("cairo/الإجازات_الرسمية_2026.csv", rows)
    assert "﻿" not in text and "المناسبة: عيد الفطر | التاريخ: 2026-03-20 | عدد الأيام: 3" in text
    assert docs[0].metadata["language"] == "ar"
    for rel in ("cairo/ساعات_العمل_في_رمضان.md", "cairo/بدل_الانتقالات.md"):
        src = (CORPUS / rel).read_text(encoding="utf-8")
        assert nfkc(src) == unicodedata.normalize("NFC", src), "NFKC leaves this Arabic text unchanged"
    assert nfkc(raw).replace("﻿", "") == raw.replace("﻿", "")


def test_ocr_repair_fixes_digits_and_letters_but_not_product_names():
    fixed, n = repair_ocr("Unused PT0 up t0 1O days, $5O/day, Effective: Jan 1 2O17, R2 and R3, P0LICY")
    assert fixed == "Unused PTO up to 10 days, $50/day, Effective: Jan 1 2017, R2 and R3, POLICY" and n == 6
    assert load(CORPUS / "scanned_archive" / "PTO_Policy_2017_scan.txt", "scanned-archive").meta["effective_date"] \
        == "2017-01-01"


def test_draft_status_comes_from_the_document_not_the_folder(rows):
    _, docs, report = text_of("policies/hr/DRAFT_HR-POL-004_PTO_v4_flexible_time_off.md", rows)
    assert report["parsed"]["status"] == "draft" and report["parsed"]["proposed_effective_date"] == "2027-01-01"
    assert "effective_date" not in report["parsed"], "a proposed date is not an effective date"
    assert all("DRAFT, not approved" in d.page_content.split("\n")[0] for d in docs)


@pytest.mark.corpus
def test_every_document_in_the_corpus_loads(rows):
    """190 listed documents, 0 skipped: nothing fails to parse."""
    failures = []
    for rel, row in rows.items():
        try:
            docs, report = build_chunks(CORPUS / rel, rel, row, 800, 100)
            if not docs:
                failures.append((rel, report.get("reason")))
        except Exception as e:                       # pragma: no cover - the failure message is the point
            failures.append((rel, repr(e)))
    assert not failures and len(rows) == 190


def test_restricted_metadata_travels_with_every_chunk(rows):
    _, docs, _ = text_of("hr_restricted/Salary_Bands_2026.xlsx", rows)
    assert docs and all(d.metadata["acl_groups"] == "hr" for d in docs)
    assert Path(docs[0].metadata["path"]).parent.name == "hr_restricted"
