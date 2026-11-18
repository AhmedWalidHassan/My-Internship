"""
Task 1 — the "recursive" view of the corpus for the UNCHANGED Week 2 loader.

The Week 2 loader (`ingest()` in week1/capstone_internal_docs_assistant/app.py) lists
DATA_DIR with `iterdir()`: top level only, `.md` / `.txt` only. Pointed at week3/corpus
it indexes exactly one file, the export's README.md, and silently skips the other 190
(they all live in sub-folders). That is the literal baseline ("W2 as shipped").

To also measure what the Week 2 *pipeline* (chunker, hybrid retriever, graph, judges) does
on the part of the corpus it can parse, this script builds a flat folder of symlinks to
every `.md` / `.txt` file under the corpus: exactly the file list a recursive walk
(`rglob` instead of `iterdir`) would feed the same loader. No product code changes;
only DATA_DIR changes. Every other format (PDF, HTML, XLSX, CSV) is still skipped, as
the Week 2 loader would skip it.

    python week3/task_01_meet_the_corpus/scripts/corpus_view.py            # prints the folder
    DATA_DIR=$(python .../corpus_view.py) make cost                          # use it

The basenames in the corpus are unique, so flattening loses nothing (checked below).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS = REPO_ROOT / "week3" / "corpus"
W2_SUPPORTED_EXT = (".md", ".txt")          # SUPPORTED_EXT in the capstone, unchanged
DEFAULT_OUT = Path(tempfile.gettempdir()) / "northwind_w3_recursive_view"


def w2_readable(corpus: Path = CORPUS) -> list[Path]:
    """Every file a recursive walk would hand the Week 2 loader."""
    return sorted(p for p in corpus.rglob("*") if p.is_file() and p.suffix.lower() in W2_SUPPORTED_EXT)


def build_view(corpus: Path = CORPUS, out: Path = DEFAULT_OUT) -> tuple[Path, list[Path]]:
    files = w2_readable(corpus)
    names = [p.name for p in files]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:                     # the Week 2 manifest keys on the basename: a clash would drop a file
        raise SystemExit(f"basename clash, flattening would lose files: {dupes}")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for p in files:
        (out / p.name).symlink_to(p.resolve())
    # Not read by the Week 2 loader (.csv), but it marks this folder as the Week 3 corpus, so the
    # live tests pick the Week 3 expectations (tests/test_golden_path.py::CORPUS_FACTS).
    (out / "_metadata.csv").symlink_to((corpus / "_metadata.csv").resolve())
    return out, files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    out, files = build_view(args.corpus, args.out)
    print(f"{len(files)} .md/.txt files linked", file=sys.stderr)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
