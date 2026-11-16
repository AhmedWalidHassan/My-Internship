"""
Latency benchmark for the running API (Week 2, Task 3). A pure HTTP client.

    make run                                   # terminal 1
    make bench-api                             # terminal 2: 20 x /chat, then 20 x /chat/stream
    python scripts/bench_api.py --concurrency 5     # stretch: 5 at once vs the same 5 one by one

Questions: the first N answerable questions of the capstone eval set (the same set
COST.md uses), each in a fresh session so history never changes the path. One
warm-up request (not counted) loads the model into memory first.

For /chat/stream it records, per request, when the first status event, the first
token, the last token and the `done` event arrived. "Time to last token" is when
the model finished writing; "done" is later, because the fact-check runs after
generation and only then is the answer final.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def questions(n: int) -> list[str]:
    # Only the question list is read from the capstone; no graph is built.
    from app.capstone import load_capstone

    return [q for q, _ans, src, _fact in load_capstone().EVAL_EXAMPLES if src][:n]


def pct(values, p):
    """Percentile with linear interpolation (numpy's default)."""
    xs = sorted(values)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100
    lo, hi = math.floor(k), min(math.floor(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def sse_events(resp):
    event, data = "message", []
    for line in resp.iter_lines():
        if not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))


def call_chat(client, q):
    t0 = time.perf_counter()
    r = client.post("/chat", json={"question": q, "session_id": f"bench-{uuid.uuid4()}"})
    total = time.perf_counter() - t0
    r.raise_for_status()
    body = r.json()
    return {"question": q, "total_s": total, "server_ms": body["elapsed_ms"], "path": body["node_path"],
            "refused": not body["sources"]}


def call_stream(client, q):
    row = {"question": q, "first_status_s": None, "ttft_s": None, "ttlt_s": None, "done_s": None,
           "tokens": 0, "retracts": 0, "nodes": []}
    t0 = time.perf_counter()
    with client.stream("POST", "/chat/stream",
                       json={"question": q, "session_id": f"bench-{uuid.uuid4()}"}) as r:
        r.raise_for_status()
        for event, data in sse_events(r):
            now = time.perf_counter() - t0
            if event == "status":
                row["first_status_s"] = row["first_status_s"] or now
                row["nodes"].append((data["node"], data["elapsed_ms"]))
            elif event == "token":
                row["ttft_s"] = row["ttft_s"] or now
                row["ttlt_s"] = now
                row["tokens"] += 1
            elif event == "retract":
                row["retracts"] += 1
            elif event == "done":
                row["done_s"] = now
                row["path"] = data["node_path"]
                row["refused"] = not data["sources"]
            elif event == "error":
                raise RuntimeError(f"stream error: {data}")
    return row


def node_durations(rows):
    """Seconds spent per node type, from the status events' server-side timestamps."""
    per = {}
    for r in rows:
        prev = 0
        for node, ms in r["nodes"]:
            per.setdefault(node, []).append((ms - prev) / 1000)
            prev = ms
    return per


def summarize(label, values, unit_ms=True):
    f = 1000 if unit_ms else 1
    return (f"| {label} | {pct(values, 50) * f:,.0f} ms | {pct(values, 95) * f:,.0f} ms | "
            f"{len(values)} |")


def run_sequential(client, qs):
    print(f"\n/chat x{len(qs)} ...", flush=True)
    chat = []
    for i, q in enumerate(qs, 1):
        chat.append(call_chat(client, q))
        print(f"  {i:2d}. {chat[-1]['total_s']:6.2f}s  {q}", flush=True)
    print(f"\n/chat/stream x{len(qs)} ...", flush=True)
    stream = []
    for i, q in enumerate(qs, 1):
        stream.append(call_stream(client, q))
        s = stream[-1]
        ttft = f"{s['ttft_s']:.2f}s" if s["ttft_s"] else "  -  "
        print(f"  {i:2d}. ttft {ttft}  done {s['done_s']:6.2f}s  {s['tokens']:3d} tokens  {q}", flush=True)

    with_tokens = [s for s in stream if s["ttft_s"] is not None]
    lines = [
        "| Endpoint | p50 latency | p95 latency | n |",
        "|---|---:|---:|---:|",
        summarize("`POST /chat`", [c["total_s"] for c in chat]),
        summarize("`POST /chat/stream` (time to first token)", [s["ttft_s"] for s in with_tokens]),
        summarize("`POST /chat/stream` (time to last token)", [s["ttlt_s"] for s in with_tokens]),
        summarize("`POST /chat/stream` (time to `done`, answer final)", [s["done_s"] for s in stream]),
        summarize("`POST /chat/stream` (first status event)", [s["first_status_s"] for s in stream]),
    ]
    extra = {
        "chat_mean_s": statistics.mean(c["total_s"] for c in chat),
        "stream_done_mean_s": statistics.mean(s["done_s"] for s in stream),
        "stream_without_tokens": [s["question"] for s in stream if s["ttft_s"] is None],
        "stream_retracts": sum(s["retracts"] for s in stream),
        "chat_paths_with_rewrite": sum("rewrite_query" in c["path"] for c in chat),
        "stream_paths_with_rewrite": sum("rewrite_query" in s["path"] for s in stream),
    }
    return {"chat": chat, "stream": stream, "table": lines, "extra": extra}


def run_concurrency(client, qs, k):
    qs = qs[:k]
    print(f"\nconcurrency: the same {k} questions one at a time, then all {k} at once ...", flush=True)
    seq = [call_stream(client, q) for q in qs]
    par, errors = [None] * k, []

    def worker(i, q):
        try:
            with httpx.Client(base_url=client.base_url, timeout=client.timeout) as c:
                par[i] = call_stream(c, q)
        except Exception as e:                       # record, don't hide
            errors.append(f"{q}: {e}")

    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(i, q)) for i, q in enumerate(qs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0
    par = [p for p in par if p]

    seq_nodes, par_nodes = node_durations(seq), node_durations(par)
    lines = [
        f"| | one at a time (x{k}) | {k} at once |",
        "|---|---:|---:|",
        f"| wall clock for all {k} | {sum(s['done_s'] for s in seq):.1f} s | {wall:.1f} s |",
        f"| per-request latency p50 (to `done`) | {pct([s['done_s'] for s in seq], 50):.1f} s | "
        f"{pct([p['done_s'] for p in par], 50):.1f} s |",
        f"| per-request latency max | {max(s['done_s'] for s in seq):.1f} s | "
        f"{max(p['done_s'] for p in par):.1f} s |",
        f"| time to first token p50 | {pct([s['ttft_s'] for s in seq if s['ttft_s']], 50):.1f} s | "
        f"{pct([p['ttft_s'] for p in par if p['ttft_s']], 50):.1f} s |",
        "",
        "| node (mean seconds per call) | one at a time | at once | slowdown |",
        "|---|---:|---:|---:|",
    ]
    for node in seq_nodes:
        a = statistics.mean(seq_nodes[node])
        b = statistics.mean(par_nodes.get(node, [float("nan")]))
        lines.append(f"| `{node}` | {a:.2f} | {b:.2f} | {b / a if a > 0.005 else float('nan'):.1f}x |")
    return {"sequential": seq, "parallel": par, "wall_s": wall, "errors": errors, "table": lines}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--concurrency", type=int, default=0, help="also run the K-at-once test (stretch)")
    p.add_argument("--skip-sequential", action="store_true")
    p.add_argument("--out", type=Path, help="write raw rows + tables as JSON")
    args = p.parse_args(argv)

    qs = questions(args.n)
    client = httpx.Client(base_url=args.url, timeout=httpx.Timeout(300.0, connect=5.0))
    ready = client.get("/readyz")
    if ready.status_code != 200:
        sys.exit(f"API not ready: {ready.text}")
    print("readyz:", ready.json())
    print("warm-up (not counted):", f"{call_chat(client, 'How many sick days do I get?')['total_s']:.2f}s")

    result = {"url": args.url, "date": time.strftime("%Y-%m-%d %H:%M:%S"), "n": len(qs)}
    if not args.skip_sequential:
        result["sequential"] = run_sequential(client, qs)
        print("\n" + "\n".join(result["sequential"]["table"]))
        print(json.dumps(result["sequential"]["extra"], indent=2))
    if args.concurrency:
        result["concurrency"] = run_concurrency(client, qs, args.concurrency)
        print("\n" + "\n".join(result["concurrency"]["table"]))
        if result["concurrency"]["errors"]:
            print("errors:", result["concurrency"]["errors"])
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
