"""
Week 3 Task 3 — ingestion that tells the truth.

One loader per format (PDF, HTML, XLSX, CSV, Markdown, text), Unicode normalisation, metadata
from `_metadata.csv` plus fields parsed from the document text, within-document boilerplate
removal and duplicate detection. The capstone's `ingest()` (incremental, hashed, persisted)
calls `build_chunks()` for every document of a corpus export; see `pipeline.py`.

Bump LOADER_VERSION whenever parsing changes what a chunk contains: it is part of the index
signature, so a changed loader rebuilds the index instead of mixing old and new chunks.
"""

from ingest.pipeline import LOADER_VERSION, EXPORT_EXT, build_chunks, corpus_snapshot, read_metadata

__all__ = ["LOADER_VERSION", "EXPORT_EXT", "build_chunks", "corpus_snapshot", "read_metadata"]
