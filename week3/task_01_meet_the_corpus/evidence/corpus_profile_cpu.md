# Corpus profile

Chunking 800/100, embeddings `sentence-transformers/all-MiniLM-L6-v2`. 190 documents in `_metadata.csv`.

**Literal** (W2 loader on `week3/corpus`): indexes ['README.md'] (the export's own note, not a corpus document) and **0 of 190** documents.
**Recursive** (W2 loader, every .md/.txt): **118 of 190** loaded, 54,962 chars, 139 chunks.
**Full** (reference extractor, all formats): 206,709 chars.

| Source system | Documents | Loaded, literal | Loaded, recursive | W2 chunks | Chars (full extract) |
|---|---:|---:|---:|---:|---:|
| drive | 113 | 0 | 106 | 107 | 159,607 |
| wiki | 34 | 0 | 3 | 3 | 18,431 |
| policy-portal | 19 | 0 | 1 | 5 | 15,292 |
| intranet | 16 | 0 | 0 | 0 | 6,531 |
| intranet-legacy | 4 | 0 | 4 | 20 | 6,139 |
| scanned-archive | 4 | 0 | 4 | 4 | 709 |

| Format | Documents | Loaded, literal | Loaded, recursive | W2 chunks | Chars (full extract) |
|---|---:|---:|---:|---:|---:|
| txt | 104 | 0 | 104 | 104 | 44,404 |
| html | 46 | 0 | 0 | 0 | 23,435 |
| pdf | 23 | 0 | 0 | 0 | 115,769 |
| md | 14 | 0 | 14 | 35 | 10,558 |
| xlsx | 2 | 0 | 0 | 0 | 12,173 |
| csv | 1 | 0 | 0 | 0 | 370 |

Languages (langdetect, per document): ar 4, en 186

## Index builds (measured, cpu; model load 3.28 s not included)

| View | Files | Chunks | Chars | Embedding tokens (cl100k) | Build wall clock | Index on disk | Cost @ $0.02/1M |
|---|---:|---:|---:|---:|---:|---:|---:|
| week2 corpus (week1/data) | 4 | 20 | 6,110 | 1,439 | 0.23 s | 40 KiB | $0.000029 |
| literal (W2 loader, week3/corpus) | 1 | 7 | 2,875 | 722 | 0.11 s | 15 KiB | $0.000014 |
| recursive (W2 loader, all .md/.txt) | 119 | 146 | 57,992 | 15,184 | 1.74 s | 321 KiB | $0.000304 |
| full (all 190, reference extractor) | 190 | 378 | 214,907 | 52,609 | 4.94 s | 875 KiB | $0.001052 |

## Data-quality evidence

```json
{
 "pdf_ligatures": {
  "docs": 20,
  "of": 23,
  "occurrences": 605,
  "examples": [
   "Classiﬁcation",
   "Conﬁdential",
   "Conﬁguration",
   "Deﬁning",
   "Eﬀective",
   "Oﬀ",
   "certiﬁcations",
   "certiﬁed",
   "conﬁrm",
   "modiﬁcations",
   "oﬀ",
   "oﬃce"
  ]
 },
 "ids_split_across_lines": {
  "policies/finance/FIN-POL-001_expense_reimbursement.pdf": [
   "FIN-POL-001"
  ],
  "policies/it/IT-STD-001_data_classification.pdf": [
   "IT-STD-001"
  ],
  "policies/it/IT-STD-009_lost_or_stolen_devices.pdf": [
   "IT-STD-009"
  ],
  "product/Spare_Parts_Catalog_2026.pdf": [
   "BMP-RING3"
  ]
 },
 "ocr_suspect_tokens": {
  "scanned_archive/Expense_Policy_2019_scan.txt": [
   "$1O",
   "$5O",
   "$8O",
   "6O",
   "Mea1s",
   "P0LICY",
   "al1",
   "f0r",
   "internationa1",
   "travel1ing"
  ],
  "scanned_archive/Handbook_2016_cover_scan.txt": [
   "2O16",
   "HANDB00K",
   "al1"
  ],
  "scanned_archive/PTO_Policy_2017_scan.txt": [
   "0FF",
   "0f",
   "1O",
   "2O17",
   "Ful1",
   "NORTHW1ND",
   "P0LICY",
   "PT0",
   "R0B0TICS",
   "emp1oyees",
   "fo11owing",
   "t0"
  ],
  "scanned_archive/Travel_Policy_2018_scan.txt": [
   "$18O",
   "2O18",
   "Al1",
   "Hote1s",
   "c1ass",
   "durati0n",
   "f1ights",
   "regard1ess",
   "t0"
  ]
 },
 "manual_boilerplate": {
  "sentences": 1099,
  "distinct": 204,
  "share_that_are_repeats": 0.814,
  "top": [
   [
    "Operators must complete the Northwind certiﬁed operator course before using the ",
    83
   ],
   [
    "Always conﬁrm that the work area is clear of personnel before starting an autono",
    83
   ],
   [
    "Firmware updates are staged to a canary group before ﬂeet-wide rollout.",
    82
   ]
  ]
 },
 "pdf_furniture_lines": [
  [
   "Northwind Robotics - Warehouse Rover RN Operator Manual - Rev C - Page N of N",
   23
  ],
  [
   "Northwind Robotics - INTERNAL - Page N of N",
   18
  ],
  [
   "Northwind Robotics Policy Portal | Controlled copy - printed copies are uncontrolled",
   17
  ],
  [
   "Page N of N",
   4
  ],
  [
   "Northwind Robotics | Product Data Sheet",
   2
  ]
 ],
 "wiki_chrome_share": 0.565,
 "text_dated_after_last_modified": [
  {
   "doc": "wiki/sales/Demo_Rover_Booking.html",
   "last_modified": "2026-04-15",
   "mentions": "July 2026",
   "context": " Demo units ship from Austin or Berlin. R2 demo units were retired in July 2026. Last edi"
  }
 ],
 "utf8_bom": [
  "cairo/الإجازات_الرسمية_2026.csv"
 ],
 "meetings_lexical_traps": {
  "carry.over": {
   "docs": 35,
   "of": 100
  },
  "\\bPTO\\b": {
   "docs": 53,
   "of": 100
  },
  "\\bVPN\\b": {
   "docs": 38,
   "of": 100
  },
  "password": {
   "docs": 23,
   "of": 100
  }
 },
 "near_duplicate_chunks": {
  "chunks": 378,
  "pairs_jaccard_ge_0.8": 4,
  "chunks_involved": 5,
  "within_doc_top": [
   [
    "product/R3/R3_Operator_Manual_RevC.pdf",
    3
   ]
  ],
  "cross_doc_top": [
   [
    "policies/hr/HR-POL-010_remote_work.pdf ~ policies/it/IT-STD-003_password_and_authentication.pdf",
    1
   ]
  ]
 }
}
```
