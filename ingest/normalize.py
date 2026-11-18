"""Text normalisation shared by every loader."""

from __future__ import annotations

import re
import unicodedata

ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
LATIN = re.compile(r"[A-Za-z]")


def nfkc(text: str) -> str:
    """Unicode NFKC: ligatures (ﬀ ﬁ ﬂ ﬃ) become plain letters, full-width forms collapse.
    Arabic letters are unchanged by NFKC (tests/test_ingest.py checks that), but Arabic
    presentation forms, if any, fold into the base letters, which is what search needs."""
    return unicodedata.normalize("NFKC", text).replace("﻿", "")


# "IT-\nSTD-009", "FIN-\nPOL-001", "NW-BMP-\nRING3": an identifier broken at its own hyphen.
_SPLIT_ID = re.compile(r"\b([A-Z]{2,4}(?:-[A-Z0-9]+)*-)\s*\n\s*([A-Z0-9]{2,}(?:-[A-Z0-9]+)*)\b")


def rejoin_ids(text: str) -> str:
    return _SPLIT_ID.sub(r"\1\2", text)


def clean(text: str) -> str:
    """NFKC, rejoined identifiers, tidy whitespace (keeps paragraph breaks)."""
    text = rejoin_ids(nfkc(text))
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def language(text: str) -> str:
    """'ar' or 'en' by script share. The corpus has exactly these two languages (Task 1), and a
    script test is deterministic, unlike langdetect without a fixed seed."""
    ar, la = len(ARABIC.findall(text)), len(LATIN.findall(text))
    if ar + la == 0:
        return "und"
    return "ar" if ar >= la else "en"


# OCR: 0<->O and 1<->l/I inside numbers and words ("$5O/day", "1O days", "emp1oyees", "P0LICY").
_NUMLIKE = re.compile(r"(?<![A-Za-z])\$?[0-9OolI]*[0-9][0-9OolI]*(?![A-Za-z])")


def repair_ocr(text: str) -> tuple[str, int]:
    """Undo the scanner's letter/digit confusions. Returns (text, number of tokens fixed).
    Numbers: O/o -> 0 and l/I -> 1 inside a token that is otherwise digits ("2O17", "$5O").
    Words: 0 -> O/o and 1 -> l/I inside a token that is otherwise letters ("emp1oyees",
    "P0LICY", "PT0"). Product names like "R2"/"R3" are untouched (2 and 3 are never swapped)."""
    fixes = 0

    def num(m):
        nonlocal fixes
        s = m.group(0)
        t = s.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
        fixes += t != s
        return t

    def word(m):
        nonlocal fixes
        s = m.group(0)
        letters = [c for c in s if c.isalpha()]
        if not letters or not re.search(r"[01]", s) or re.search(r"[2-9]", s):
            return s
        upper = sum(c.isupper() for c in letters) > len(letters) / 2
        t = s.replace("0", "O" if upper else "o").replace("1", "I" if upper else "l")
        fixes += t != s
        return t

    text = _NUMLIKE.sub(num, text)                      # numbers first: "1O days" is 10, not "IO"
    text = re.sub(r"\b[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*\b", word, text)
    return text, fixes


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_NUMBERING = re.compile(r"^\d+(?:\.\d+)*\s+")


def drop_repeated_sentences(paragraphs: list[str], seen: set[str] | None = None) -> tuple[list[str], int]:
    """Within ONE document: remove sentences already said earlier in it (the R3 manual repeats
    the same ~10 safety sentences 80+ times). A sentence's leading section number ("9.1 ") is
    ignored when comparing, and kept on the first occurrence. Returns (paragraphs, dropped)."""
    seen = set() if seen is None else seen
    out, dropped = [], 0
    for para in paragraphs:
        kept = []
        for sent in SENTENCE.split(para):
            key = _NUMBERING.sub("", sent).strip().lower()
            if len(key) > 25 and key in seen:
                dropped += 1
                continue
            seen.add(key)
            kept.append(sent)
        text = " ".join(kept).strip()
        if text and not re.fullmatch(r"\d+(?:\.\d+)*\.?", text):     # a bare "9.4" left over: drop
            out.append(text)
    return out, dropped
