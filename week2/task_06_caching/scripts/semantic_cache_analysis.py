"""
Should there be a semantic cache? Measure it before deciding (Week 2, Task 6, layer 3).

A semantic cache serves a stored answer when a new question's embedding is within a
cosine threshold of a cached one. It is only safe if some threshold accepts
PARAPHRASES (same answer) while rejecting NEAR-MISSES (similar wording, different
answer). This script embeds both kinds of pairs with the assistant's own embedding
model and reports, per threshold, how many paraphrases would hit and how many
near-misses would be served the WRONG answer.

    python week2/task_06_caching/scripts/semantic_cache_analysis.py [--out file.md]

Every near-miss pair below has a different answer in week1/data (checked by hand;
the facts are in the third column).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import app.config  # noqa: E402,F401  (week1 on sys.path)

# Same question, different words: a semantic cache SHOULD serve the stored answer.
PARAPHRASES = [
    ("How many vacation days do I get a year?", "How much PTO do I get?"),
    ("How many sick days are there per year?", "How many paid sick days do I get?"),
    ("How long do I have to file an expense report?", "What's the deadline for submitting expenses?"),
    ("What are the password rules?", "What is the password policy?"),
    ("How much weight can the Warehouse Rover R2 carry?", "What is the R2's payload capacity?"),
    ("How do I get on the VPN from home?", "How do I connect to the VPN remotely?"),
    ("What is my annual learning budget?", "How much training budget do I get per year?"),
    ("Is alcohol reimbursable?", "Can I expense alcohol?"),
    ("My laptop got stolen, what do I do?", "What should I do if my laptop is stolen?"),
    ("How often are performance reviews held?", "When are performance reviews?"),
]

# Similar wording, DIFFERENT answer: a semantic cache must NOT serve one for the other.
NEAR_MISSES = [
    ("What is the daily meal limit when travelling abroad?", "What is the daily meal limit for domestic travel?",
     "$110 vs $75"),
    ("How long is paid leave for an adoptive parent?", "How long is paid leave for a birth parent?",
     "10 vs 16 weeks"),
    ("How fast does the rover go with a load?", "How fast does the rover go without a load?",
     "1.8 vs 2.2 m/s"),
    ("Can I open our source code on my personal phone?", "Can I open my email on my personal phone?",
     "prohibited vs allowed"),
    ("What does premium support include?", "What does standard support include?",
     "24/7 + 1 h SLA vs business hours + 4 h"),
    ("How many vacation days do I get a year?", "How many sick days do I get a year?", "20 vs 10"),
    ("Can I carry over unused PTO?", "Can I carry over unused learning budget?", "up to 5 days vs no"),
    ("What is the home-office stipend?", "What is the annual learning budget?", "$500 vs $1,500"),
    ("Is alcohol reimbursable?", "Are meals reimbursable?", "no vs up to $75/$110 a day"),
    ("How far ahead do I have to ask for PTO?", "How long do I have to file an expense report?",
     "5 business days ahead vs within 30 days"),
]

THRESHOLDS = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)

    from common.settings import get_settings
    from common.utils import _base_embeddings          # the real model, without the cache

    s = get_settings()
    emb = _base_embeddings(s)
    model = getattr(emb, "model_name", None) or getattr(emb, "model", "?")

    def sims(pairs):
        flat = [q for pair in pairs for q in pair[:2]]
        vecs = emb.embed_documents(flat)
        return [cosine(vecs[2 * i], vecs[2 * i + 1]) for i in range(len(pairs))]

    para, near = sims(PARAPHRASES), sims(NEAR_MISSES)

    L = [f"# Semantic cache: can a threshold tell paraphrases from near-misses?\n",
         f"Embedding model: `{model}` (the assistant's own). Cosine similarity of each pair.\n",
         "## Paraphrases (same answer: a semantic cache should hit)\n",
         "| Cosine | Question A | Question B |", "|---:|---|---|"]
    L += [f"| {c:.3f} | {a} | {b} |" for c, (a, b) in sorted(zip(para, PARAPHRASES), reverse=True)]
    L += ["\n## Near-misses (different answer: a semantic cache must NOT hit)\n",
          "| Cosine | Question A | Question B | Different answers |", "|---:|---|---|---|"]
    L += [f"| {c:.3f} | {a} | {b} | {f} |" for c, (a, b, f) in sorted(zip(near, NEAR_MISSES), reverse=True)]
    L += ["\n## Per threshold\n",
          "| Threshold | Paraphrases served from cache (good) | Near-misses served the WRONG answer |",
          "|---:|---:|---:|"]
    for t in THRESHOLDS:
        good = sum(c >= t for c in para)
        bad = sum(c >= t for c in near)
        L.append(f"| {t:.2f} | {good}/{len(para)} | **{bad}/{len(near)}** |")
    safe = [t for t in THRESHOLDS if all(c < t for c in near)]
    max_near = max(near)
    L.append(f"\nHighest near-miss similarity: **{max_near:.3f}**. Lowest paraphrase similarity: "
             f"{min(para):.3f}. Paraphrases above the highest near-miss: "
             f"**{sum(c > max_near for c in para)}/{len(para)}**.")
    if safe:
        t = safe[0]
        L.append(f"The lowest threshold with zero wrong answers here is {t:.2f}, where "
                 f"{sum(c >= t for c in para)}/{len(para)} paraphrases would hit.")
    report = "\n".join(L)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
