"""
Task 4 — fill an experiment's "Result" block in week3/EXPERIMENTS.md from its evidence JSON
(overall table + every category that moved), followed by the written conclusion.

    python week3/task_04_retrieval_experiments/scripts/write_result.py EXP-01 conclusions/EXP-01.md
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
EXPERIMENTS = HERE.parents[0] / "EXPERIMENTS.md"
CATS = ("factual", "table", "keyword", "version", "conflict", "draft", "multi_hop", "multi_part", "ambiguous",
        "long_doc", "cross_lingual", "follow_up", "personalized", "access")


def block(exp_id: str, conclusion: str, latency_note: str = "") -> str:
    b = json.loads((HERE / "evidence" / "baseline-1_dev.json").read_text())["retrieval"]
    x = json.loads((HERE / "evidence" / f"{exp_id}_dev.json").read_text())["retrieval"]
    bo, xo = b["overall"], x["overall"]

    def real(d, n=60, metric="r"):
        if abs(d) < 1e-9:
            return "no (identical)"
        return "yes" if (abs(d) >= 1 / n - 1e-9 if metric == "r" else abs(d) > 0.008) else "no"

    lines = [f"**Result** *(committed after running)*: `{x['retriever']}`, {x['index']['chunks']} chunks"
             + (f", index rebuilt in {x['index']['seconds']} s" if x["index"]["rebuilt"] else "") + ".", "",
             "| | Baseline | This | Delta | Bigger than noise? |", "|---|---:|---:|---:|---|"]
    for m, label, kind in (("recall@5", "recall@5 (all)", "r"), ("mrr", "MRR (all)", "m"), ("recall@1", "recall@1 (all)", "r")):
        d = xo[m] - bo[m]
        lines.append(f"| {label} | {bo[m]:.3f} | {xo[m]:.3f} | {d:+.3f} | {real(d, metric=kind)} |")
    lines.append(f"| Latency / query (p50 / p95) | {b['latency_ms_p50']} / {b['latency_ms_p95']} ms | "
                 f"{x['latency_ms_p50']} / {x['latency_ms_p95']} ms | | {latency_note or '–'} |")
    lines.append("| Cost / query | $0 local (≈ 12 query tokens = $0.0000002 hosted) | same | 0 | – |")
    lines += ["", "Categories that moved (any recall@5 change, or MRR by more than 0.008):", "",
              "| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |", "|---|---:|---:|---:|---:|---:|"]
    for c in CATS:
        p, q = b["by_category"][c], x["by_category"][c]
        if abs(p["recall@5"] - q["recall@5"]) > 1e-9 or abs(p["mrr"] - q["mrr"]) > 0.008:
            lines.append(f"| {c} | {q['n']} | {p['recall@5']:.2f} | {q['recall@5']:.2f} | {p['mrr']:.2f} | {q['mrr']:.2f} |")
    changed = [f"{k} {'gained' if v['recall@5'] > b['per_example'][k]['recall@5'] else 'lost'}"
               for k, v in x["per_example"].items() if v["recall@5"] != b["per_example"][k]["recall@5"]]
    lines += ["", f"Questions in/out of the top 5: {', '.join(changed) or 'none'}.", "", conclusion.strip()]
    return "\n".join(lines)


def main(argv) -> int:
    exp_id, conclusion_file = argv[0], Path(argv[1])
    latency_note = argv[2] if len(argv) > 2 else ""
    text = EXPERIMENTS.read_text(encoding="utf-8")
    head = text.index(f"### {exp_id} ")
    marker = "**Result** *(committed after running)*: *(pending)*"
    pos = text.index(marker, head)
    text = text[:pos] + block(exp_id, conclusion_file.read_text(encoding="utf-8"), latency_note) + text[pos + len(marker):]
    EXPERIMENTS.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
