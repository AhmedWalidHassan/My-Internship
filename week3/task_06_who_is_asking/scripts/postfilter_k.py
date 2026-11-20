"""
Task 6 — the `k` argument against filtering AFTER retrieval, measured on the dev split.

    python week3/task_06_who_is_asking/scripts/postfilter_k.py

For every dev question, as the question's own user: search the whole index (a scope that sees every
chunk: what an unfiltered retriever returns), then drop what the user may not see (a post-filter).
Compare with the pre-filter that ships (search only what the user may see). Reports, per question,
how many of the fused top-k a post-filter would throw away, and how often the right document would
have been lost because restricted chunks took its slot.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "week1"), str(ROOT / "week2" / "task_07_eval_gate" / "scripts"),
                str(ROOT / "week3" / "task_02_eval_at_scale")]

from app.capstone import load_capstone  # noqa: E402
from app.config import get_settings  # noqa: E402
from common.access import Directory, can_see  # noqa: E402
from common.utils import get_embeddings  # noqa: E402

import run_eval  # noqa: E402


def main() -> int:
    settings = get_settings()
    cap = load_capstone()
    store, _ = cap.ingest(get_embeddings(), settings.data_dir)
    retriever, _name = cap.build_retriever(store)               # production depth (k per retriever)
    every = {g for d in store.docstore._dict.values() for g in str(d.metadata.get("acl_groups", "")).split(";") if g}
    unfiltered = retriever.for_scope(every)
    directory = Directory(settings.user_directory)
    rows, lost_total, gold_lost = [], 0, []
    dev = [e for e in run_eval.load_dataset() if e.get("split") == "dev"]
    for ex in dev:
        groups = directory.lookup(ex.get("user_id") or "u1001").groups
        q = run_eval.retrieval_query(ex)
        top = unfiltered.invoke(q)
        post = [d for d in top if can_see(d.metadata, groups)]
        pre = retriever.for_scope(groups).invoke(q)
        lost = len(top) - len(post)
        lost_total += lost
        gold = set(ex.get("gold_docs") or [])
        in_post = bool(gold & {d.metadata.get("path") for d in post[:5]})
        in_pre = bool(gold & {d.metadata.get("path") for d in pre[:5]})
        if gold and in_pre and not in_post:
            gold_lost.append(ex["id"])
        if lost:
            rows.append({"id": ex["id"], "user": ex.get("user_id"), "category": ex["category"], "top_k": len(top),
                         "dropped_by_post_filter": lost, "left": len(post), "pre_filter_returns": len(pre)})
    out = {"questions": len(dev), "k": retriever.k, "questions_losing_slots": len(rows),
           "slots_lost_total": lost_total, "gold_in_top5_pre_not_post": gold_lost, "rows": rows}
    print(json.dumps(out, indent=1))
    (ROOT / "week3" / "task_06_who_is_asking" / "evidence" / "postfilter_k.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
