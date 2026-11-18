"""
Task 8 stretch — load test: N requests spread evenly over D seconds against the RUNNING API.

    python week2/task_08_resilience/scripts/load_test.py --n 50 --seconds 30 [--url ...] [--out file.md]

Every request is a different session (the per-session rate limit doesn't apply) and the
questions cycle through the 24 answerable eval questions. Run the server with
CACHE_ENABLED=false to load the real pipeline; with the cache on, repeats are free.
Records p50/p95 latency, error rate by code, achieved throughput, and the point where
it degrades (first request that failed or took > 2x the median of the first five).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--out", type=Path)
    p.add_argument("--json", type=Path)
    args = p.parse_args(argv)
    from app.capstone import load_capstone
    questions = [q for q, _a, src, _f in load_capstone().EVAL_EXAMPLES if src]

    results = [None] * args.n
    gap = args.seconds / args.n
    t_start = time.perf_counter()

    def fire(i):
        q = questions[i % len(questions)]
        t0 = time.perf_counter()
        try:
            with httpx.Client(base_url=args.url, timeout=300) as c:
                r = c.post("/chat", json={"question": q, "session_id": f"load-{uuid.uuid4()}"})
            code = "ok" if r.status_code == 200 else r.json().get("error", str(r.status_code))
            status = r.status_code
        except Exception as e:
            code, status = f"client:{type(e).__name__}", 0
        results[i] = {"i": i, "sent_at": round(t0 - t_start, 2), "latency_s": round(time.perf_counter() - t0, 2),
                      "status": status, "code": code}

    threads = []
    for i in range(args.n):
        delay = t_start + i * gap - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        th = threading.Thread(target=fire, args=(i,))
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    wall = time.perf_counter() - t_start

    ok = [r for r in results if r["code"] == "ok"]
    lat_ok = [r["latency_s"] for r in ok]
    codes = Counter(r["code"] for r in results)
    base = sorted(r["latency_s"] for r in results[:5] if r["code"] == "ok")
    ref = base[len(base) // 2] if base else 0
    degrade = next((r for r in results if r["code"] != "ok" or (ref and r["latency_s"] > 2 * ref)), None)
    L = [f"## Load test: {args.n} requests over {args.seconds:.0f} s ({args.n / args.seconds:.2f} req/s offered)", "",
         "| p50 | p95 | Error rate | Point where it degrades |", "|---:|---:|---:|---|",
         f"| {pct(lat_ok, 50):.1f} s | {pct(lat_ok, 95):.1f} s | {100 * (args.n - len(ok)) / args.n:.0f}% "
         f"({args.n - len(ok)}/{args.n}) | "
         + (f"request #{degrade['i'] + 1} (sent at {degrade['sent_at']:.1f} s, ~{(degrade['i'] + 1) / max(degrade['sent_at'], 0.1):.2f} req/s so far): "
            f"{degrade['code']} after {degrade['latency_s']:.1f} s" if degrade else "did not degrade") + " |",
         "", f"Outcomes: {dict(codes)}. Completed {len(ok)} answers in {wall:.0f} s wall clock = "
             f"{len(ok) / wall:.2f} answers/s served. Latency of the first five: {', '.join(f'{x:.1f}' for x in base)} s."]
    L += ["", "| # | sent at | latency | result |", "|---:|---:|---:|---|"]
    L += [f"| {r['i'] + 1} | {r['sent_at']:.1f} s | {r['latency_s']:.1f} s | {r['code']} |" for r in results]
    report = "\n".join(L)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
