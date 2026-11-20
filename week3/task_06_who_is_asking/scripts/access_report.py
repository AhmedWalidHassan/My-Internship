"""
Task 6 — leaks in an eval run, from its results file alone.

    python week3/task_06_who_is_asking/scripts/access_report.py <run.json> [--out report.md]

For EVERY example of the run (not only the `access` category), against the real directory and ACLs:
  * retrieval leak: a document the example's user may not see is in its retrieved (or kept) documents;
  * answer leak:    a `must_not_include` string of an `access` example is in the answer.
And for the `access` category: was each authorised user answered (deterministic score), and was each
unauthorised user given the standard refusal?
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "week3" / "corpus"
DATASET = ROOT / "week3" / "eval" / "eval_v3.jsonl"


def groups(raw: str) -> set:
    return {g for g in (raw or "").split(";") if g}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    with open(CORPUS / "_directory.csv", encoding="utf-8") as f:
        users = {r["user_id"]: groups(r["groups"]) for r in csv.DictReader(f)}
    with open(CORPUS / "_metadata.csv", encoding="utf-8") as f:
        acl = {r["path"]: groups(r["acl_groups"]) for r in csv.DictReader(f)}
    examples = [json.loads(x) for x in DATASET.read_text(encoding="utf-8").splitlines() if x.strip()]
    spec = {e["id"]: e for e in examples}
    run = json.loads(a.run.read_text(encoding="utf-8"))
    rows = run["examples"]

    retrieval_leaks, answer_leaks, access = [], [], []
    for r in rows:
        user = users.get(r.get("user_id") or "u1001", set())
        hidden = sorted({d for d in (r.get("retrieved_docs") or []) + (r.get("kept_docs") or [])
                         if d in acl and acl[d] != {"all"} and not (acl[d] & user)})
        if hidden:
            retrieval_leaks.append((r["id"], r.get("user_id"), hidden))
        ex = spec.get(r["id"], {})
        answer = r.get("answer") or ""
        bad = [s for s in ex.get("must_not_include", []) if s and s.lower() in answer.lower()]
        if r["category"] == "access":
            authorised = bool(ex.get("gold_docs"))
            if bad:
                answer_leaks.append((r["id"], r.get("user_id"), bad))
            access.append({"id": r["id"], "user": r.get("user_id"), "authorised": authorised,
                           "refused": r.get("refused"), "deterministic": r["scores"].get("deterministic"),
                           "leak": bool(bad or hidden), "answer": answer[:90].replace("\n", " ")})

    auth = [x for x in access if x["authorised"]]
    unauth = [x for x in access if not x["authorised"]]
    L = [f"# Access report: `{a.run.name}`\n",
         f"- Examples checked: {len(rows)} (every category). Retrieval leaks: **{len(retrieval_leaks)}**. "
         f"Answer leaks (`access`): **{len(answer_leaks)}**.",
         f"- `access` category: {len(access)} examples. Unauthorised users refused without a leak: "
         f"**{sum(1 for x in unauth if x['refused'] and not x['leak'])}/{len(unauth)}**. "
         f"Authorised users answered (deterministic): **{sum(1 for x in auth if x['deterministic'])}/{len(auth)}**.\n",
         "| id | user | allowed? | refused | deterministic | leak | answer |", "|---|---|---|---|---:|---|---|"]
    L += [f"| {x['id']} | {x['user']} | {'yes' if x['authorised'] else 'no'} | {x['refused']} | {x['deterministic']} | "
          f"{'**LEAK**' if x['leak'] else 'no'} | {x['answer']} |" for x in access]
    if retrieval_leaks:
        L += ["\nRetrieval leaks (documents the user may not see, in the retrieved/kept set):", ""]
        L += [f"- {i} ({u}): {', '.join(d)}" for i, u, d in retrieval_leaks]
    if answer_leaks:
        L += ["\nAnswer leaks (must_not_include found in the answer):", ""]
        L += [f"- {i} ({u}): {', '.join(b)}" for i, u, b in answer_leaks]
    text = "\n".join(L) + "\n"
    print(text)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
