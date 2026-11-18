"""
Task 2 — generate CANDIDATE eval questions from corpus chunks with an LLM.

Nothing generated here goes into the dataset automatically. Every candidate is reviewed
(accepted / rejected with a reason) in `candidates_reviewed.jsonl`, and only accepted ones,
often edited, become examples in week3/eval/eval_v3.jsonl. The acceptance rate is recorded in
week3/RESULTS.md.

    python week3/task_02_eval_at_scale/synth/generate_candidates.py      # -> candidates.jsonl

Chunks come from the documents behind the categories the merged set is short of (table,
long_doc, cross_lingual, keyword/multi-hop facts in product docs). The text is pulled with the
Task 1 reference extractor (PDF/XLSX/HTML included, even though the Week 2 loader can't read
them yet) and cut by the Week 2 chunker (800/100), so candidates look like what a user would
ask about those passages. Model: the generator (qwen3.5:4b, temperature 0). Questions about
Arabic passages are requested in English (the cross_lingual category).
"""

from __future__ import annotations

import json
import random
import re
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS = REPO_ROOT / "week3" / "corpus"
OUT = Path(__file__).resolve().parent / "candidates.jsonl"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "week3" / "task_01_meet_the_corpus" / "scripts"))

from profile_corpus import extract  # noqa: E402  (Task 1 reference extractor)

TARGETS = {   # path -> how many chunks to sample (None = all)
    "policies/finance/FIN-POL-002_travel_and_per_diem.pdf": None,
    "product/Support_SLA_2026.pdf": None,
    "product/Spare_Parts_Catalog_2026.pdf": None,
    "product/R3/R3_Operator_Manual_RevC.pdf": 14,
    "product/R3/Warehouse_Rover_R3_datasheet.pdf": None,
    "product/Rover_Error_Codes_2026.xlsx": 3,
    "product/fleet_manager/release_notes_5.0.md": None,
    "cairo/دليل_مكتب_القاهرة.md": None,
    "cairo/ساعات_العمل_في_رمضان.md": None,
    "cairo/الإجازات_الرسمية_2026.csv": None,
    "wiki/people/US_Holidays_2026.html": None,
    "wiki/eng/Robotics_Lab_Safety.html": None,
    "wiki/facilities/Offices.html": None,
    "policies/hr/HR-POL-006_parental_leave.pdf": None,
    "policies/it/IT-STD-001_data_classification.pdf": None,
}

PROMPT = (
    "You write evaluation questions for an internal company assistant. Read the passage and write "
    "2 questions that an employee could ask and that THIS passage answers. Write the questions in "
    "English even if the passage is in another language. For each question give a short answer taken "
    "from the passage and one short exact fact (a number, name or phrase, as it would appear in a "
    "correct English answer) that a correct answer must contain.\n\n"
    "Passage (from {path}):\n{text}\n\n"
    'Reply with only a JSON list: [{{"question": "...", "answer": "...", "must_include": "..."}}, ...]'
)


def chunks_of(path: str) -> list[str]:
    from app.capstone import load_capstone
    cap = load_capstone()
    tmp = Path(tempfile.mkdtemp()) / (Path(path).stem + ".txt")
    tmp.write_text(extract(CORPUS / path), encoding="utf-8")
    return [d.page_content for d in cap.chunk_file(tmp)]


def main() -> int:
    from app.capstone import load_capstone
    cap = load_capstone()
    from common.utils import get_llm
    llm = get_llm(temperature=0)
    rng = random.Random(3)
    n, t0 = 0, time.perf_counter()
    with OUT.open("w", encoding="utf-8") as f:
        for path, sample in TARGETS.items():
            chunks = chunks_of(path)
            picked = sorted(rng.sample(range(len(chunks)), sample)) if sample and sample < len(chunks) \
                else range(len(chunks))
            for i in picked:
                reply = cap._ask(llm, PROMPT.format(path=path, text=chunks[i][:2500]))
                m = re.search(r"\[.*\]", reply, re.S)
                try:
                    items = json.loads(m.group(0)) if m else []
                except json.JSONDecodeError:
                    items = []
                if not items:
                    items = [{"question": None, "answer": None, "must_include": None, "raw": reply[:300]}]
                for it in items[:2]:
                    n += 1
                    f.write(json.dumps({"cid": f"c{n:03d}", "source": path, "chunk": i,
                                        "chunk_text": chunks[i][:600], **it}, ensure_ascii=False) + "\n")
                print(f"{n:3d} candidates  {path} #{i}", flush=True)
    print(f"{n} candidates in {time.perf_counter() - t0:.0f} s -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
