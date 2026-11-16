"""
Prove (or disprove) the cache's savings (Week 2, Task 6). Runs the SERVICE code path
(ChatService + the real backend, same as the API minus HTTP) with the answer cache and
a fresh embedding cache, on the local model.

    python week2/task_06_caching/scripts/cache_benchmark.py cold-warm  [--n 20]
    python week2/task_06_caching/scripts/cache_benchmark.py workload   [--requests 120 --seed 7]
    python week2/task_06_caching/scripts/cache_benchmark.py prewarm    [--n 10]
    ... add --out evidence/<file>.md to save the report

cold-warm  the same N answerable eval questions twice, each in a fresh session: pass 1
           with an empty cache (cold), pass 2 with what pass 1 left (warm).
workload   a repeated-question workload (described in WORKLOAD below) -> hit rate,
           broken down by why each request did or did not hit.
prewarm    stretch: p95 for a cold-start user asking the top N questions, without and
           with CACHE_PREWARM-style warm-up at startup.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
import time
import uuid
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# A FRESH embedding cache for every benchmark run, so "cold" really is cold. Must be set
# before the settings are first read (the capstone reads them at import).
os.environ["EMBEDDING_CACHE_PATH"] = tempfile.mkdtemp(prefix="emb-cache-bench-")
os.environ.setdefault("CACHE_ENABLED", "true")

from app.capstone import load_capstone  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.observability import Observer, percentile  # noqa: E402
from semantic_cache_analysis import PARAPHRASES  # noqa: E402

WORKLOAD = """\
**Workload (defined, deterministic: `--seed 7`):** N requests from employees, one at a time.
- **Which question:** the 28 eval questions (24 answerable + 4 out-of-scope) with Zipf-like
  popularity (weight 1/rank^1.1, rank = eval-set order), so a few questions dominate, like a
  real internal FAQ.
- **How it is asked** (first question of a new session):
  - 60%: the exact eval wording;
  - 25%: a trivial variant (lowercase, no question mark, extra spaces), which normalisation
    should absorb;
  - 15%: a real paraphrase, for the 10 questions that have one (else exact). Only a semantic
    cache could hit on those.
- **Follow-ups:** 10% of requests are instead a SECOND turn in an earlier session ("Are there
  any exceptions?", ...). They are never cacheable, by design.
"""

FOLLOW_UPS = ["Are there any exceptions?", "Who do I contact about that?", "Does that apply to contractors too?"]


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


class Collect(Observer):
    def __init__(self):
        super().__init__()
        self.records = []

    def request_finished(self, rec):
        self.records.append(dict(rec))


def build(settings):
    from app.main import build_cache, default_backend_factory
    from app.service import ChatService

    load_capstone().setup_logging()
    backend = default_backend_factory()
    obs = Collect()
    cache = build_cache(settings)
    obs.metrics.bind_cache(cache)
    return backend, obs, cache, (lambda c=cache: ChatService(backend, obs, c))


def ask(service, obs, question, session=None, rid=""):
    service.ask(question, session or f"bench-{uuid.uuid4()}", trace_id=str(uuid.uuid4()), request_id=rid)
    return obs.records[-1]


def summarize(recs):
    lat = sorted(r["latency_ms"] / 1000 for r in recs)
    return {"n": len(recs), "mean_s": mean(lat), "p50_s": percentile(lat, 50), "p95_s": percentile(lat, 95),
            "mean_cost": mean([r["estimated_cost_usd"] for r in recs]),
            "total_cost": sum(r["estimated_cost_usd"] for r in recs),
            "hits": sum(r["cache_hit"] for r in recs), "llm_calls": sum(r["llm_calls"] for r in recs)}


def fmt_s(x):
    """Seconds, readably: a cache hit is sub-millisecond (latency is logged in whole ms)."""
    return "<1 ms" if x < 0.001 else (f"{x * 1000:.0f} ms" if x < 1 else f"{x:.2f} s")


def fmt_usd(x):
    return f"${x:.6f}" if x < 0.01 else f"${x:,.4f}"


# ---------------------------------------------------------------------------
def cold_warm(args, settings):
    from common import embedding_cache

    backend, obs, cache, make_service = build(settings)
    service = make_service()
    qs = [q for q, _a, src, _f in load_capstone().EVAL_EXAMPLES if src][:args.n]
    ask(service, obs, "warm-up: what is Northwind?", rid="warmup")   # model load; not counted
    cache_entries_before = len(cache)
    obs.records.clear()
    passes = {}
    for name in ("cold", "warm"):
        e0 = embedding_cache.stats()
        start = len(obs.records)
        for i, q in enumerate(qs, 1):
            r = ask(service, obs, q, rid=f"{name}-{i:02d}")
            print(f"  {name} {i:2d}. {'HIT ' if r['cache_hit'] else 'miss'} {r['latency_ms'] / 1000:6.3f}s  {q}",
                  flush=True)
        e1 = embedding_cache.stats()
        passes[name] = summarize(obs.records[start:])
        passes[name]["emb_hits"] = e1["hits"] - e0["hits"]
        passes[name]["emb_misses"] = e1["misses"] - e0["misses"]
    c, w = passes["cold"], passes["warm"]
    L = [f"# Cache: cold vs warm, same {len(qs)} questions\n",
         f"Model `{settings.llm_label}` (local), pricing gpt-4o-mini list. Each question in a fresh session. "
         f"Answer cache entries before the cold pass: {cache_entries_before} (only the warm-up); fresh "
         f"embedding cache.\n",
         "| | Mean latency | p95 latency | Mean cost / question | Total run cost | Cache hits | LLM calls | Query embeddings computed |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, p in passes.items():
        L.append(f"| {name.capitalize()} cache | {fmt_s(p['mean_s'])} | {fmt_s(p['p95_s'])} | {fmt_usd(p['mean_cost'])} | "
                 f"{fmt_usd(p['total_cost'])} | {p['hits']}/{p['n']} | {p['llm_calls']} | {p['emb_misses']} |")
    L.append(f"| **Delta** | **−{c['mean_s'] - w['mean_s']:.2f} s ({100 * (1 - w['mean_s'] / c['mean_s']):.0f}% less)** | "
             f"**−{c['p95_s'] - w['p95_s']:.2f} s** | "
             f"**{fmt_usd(w['mean_cost'] - c['mean_cost']).replace('$-', '−$')}** | "
             f"**{fmt_usd(w['total_cost'] - c['total_cost']).replace('$-', '−$')}** | | "
             f"{w['llm_calls'] - c['llm_calls']:+d} | |")
    L.append(f"\nCold-pass misses that stayed misses in the warm pass (not cached: refusals beyond the refusal TTL, "
             f"or failed): {w['n'] - w['hits']}.")
    return "\n".join(L)


# ---------------------------------------------------------------------------
def workload(args, settings):
    from common import embedding_cache

    rng = random.Random(args.seed)
    examples = [(q, src is None) for q, _a, src, _f in load_capstone().EVAL_EXAMPLES]
    weights = [1 / (rank ** 1.1) for rank in range(1, len(examples) + 1)]
    para = {a: b for a, b in PARAPHRASES}

    plan, sessions = [], []
    for i in range(args.requests):
        if sessions and rng.random() < 0.10:
            plan.append(("follow-up", rng.choice(FOLLOW_UPS), rng.choice(sessions), None))
            continue
        q, _oos = rng.choices(examples, weights)[0]
        roll = rng.random()
        if roll < 0.60:
            kind, text = "exact", q
        elif roll < 0.85:
            kind, text = "variant", rng.choice([q.lower(), q.rstrip("?"), "  " + q.replace(" ", "  ")])
        else:
            kind, text = ("paraphrase", para[q]) if q in para else ("exact", q)
        sid = f"wl-{i}"
        sessions.append(sid)
        plan.append((kind, text, sid, q))

    backend, obs, cache, make_service = build(settings)
    service = make_service()
    ask(service, obs, "warm-up: what is Northwind?", rid="warmup")
    obs.records.clear()
    seen_canonical = set()
    outcome = Counter()
    by_kind = Counter()
    hits_by_kind = Counter()
    e0 = embedding_cache.stats()
    t0 = time.perf_counter()
    for i, (kind, text, sid, canonical) in enumerate(plan, 1):
        r = ask(service, obs, text, sid, rid=f"wl-{i:03d}")
        by_kind[kind] += 1
        hits_by_kind[kind] += r["cache_hit"]
        if r["cache_hit"]:
            outcome["hit"] += 1
        elif kind == "follow-up":
            outcome["miss: follow-up (never cached, by design)"] += 1
        elif kind == "paraphrase":
            outcome["miss: paraphrase (only a semantic cache could hit)"] += 1
        elif canonical not in seen_canonical:
            outcome["miss: first time this question was asked"] += 1
        elif r["refused"]:
            outcome["miss: refusal not cached / expired (short TTL)"] += 1
        else:
            outcome["miss: other"] += 1
        if kind != "follow-up" and kind != "paraphrase":
            seen_canonical.add(canonical)
        print(f"  {i:3d}. {'HIT ' if r['cache_hit'] else 'miss'} {kind:10s} {r['latency_ms'] / 1000:6.3f}s  {text.strip()[:60]}",
              flush=True)
    wall = time.perf_counter() - t0
    e1 = embedding_cache.stats()
    s = summarize(obs.records)
    misses = [r for r in obs.records if not r["cache_hit"]]
    no_cache_cost = mean([r["estimated_cost_usd"] for r in misses]) * len(obs.records)
    no_cache_time = mean([r["latency_ms"] / 1000 for r in misses]) * len(obs.records)
    L = [f"# Cache hit rate on a repeated-question workload ({len(plan)} requests)\n", WORKLOAD,
         f"**Hit rate: {s['hits']}/{s['n']} = {100 * s['hits'] / s['n']:.0f}%**\n",
         "| Outcome | Requests | % |", "|---|---:|---:|"]
    L += [f"| {k} | {v} | {100 * v / s['n']:.0f}% |" for k, v in outcome.most_common()]
    L += ["\n| Asked as | Requests | Hit rate |", "|---|---:|---:|"]
    L += [f"| {k} | {by_kind[k]} | {100 * hits_by_kind[k] / by_kind[k]:.0f}% |" for k in
          ("exact", "variant", "paraphrase", "follow-up") if by_kind[k]]
    L += [f"\n| | With the cache (measured) | Without (estimated: every request at the mean miss cost/latency) |",
          "|---|---:|---:|",
          f"| Total LLM cost | {fmt_usd(s['total_cost'])} | {fmt_usd(no_cache_cost)} |",
          f"| Total answer time | {sum(r['latency_ms'] for r in obs.records) / 1000:.0f} s | {no_cache_time:.0f} s |",
          f"| Mean / p95 latency | {s['mean_s']:.2f} s / {s['p95_s']:.2f} s | {mean([r['latency_ms'] / 1000 for r in misses]):.2f} s / "
          f"{percentile(sorted(r['latency_ms'] / 1000 for r in misses), 95):.2f} s (misses only) |",
          f"\nWall clock {wall:.0f} s. Embedding cache over the run: {e1['hits'] - e0['hits']} hits, "
          f"{e1['misses'] - e0['misses']} misses (query embeddings; the corpus index was loaded, not re-embedded)."]
    return "\n".join(L)


# ---------------------------------------------------------------------------
def prewarm_mode(args, settings):
    from app.main import build_cache, prewarm

    backend, obs, _cache, _make = build(settings)
    from app.service import ChatService

    qs = [q for q, _a, src, _f in load_capstone().EVAL_EXAMPLES if src][:args.n]
    ChatService(backend, obs, None).ask("warm-up: what is Northwind?", "w", trace_id=str(uuid.uuid4()))
    rows = {}
    for label, warm in (("no pre-warm", False), (f"pre-warmed ({args.n} questions)", True)):
        cache = build_cache(settings)
        service = ChatService(backend, obs, cache)
        prewarm_s = 0.0
        if warm:
            t0 = time.perf_counter()
            prewarm(service, args.n)
            prewarm_s = time.perf_counter() - t0
        start = len(obs.records)
        for i, q in enumerate(qs, 1):
            ask(service, obs, q, rid=f"user-{i:02d}")
        rows[label] = summarize(obs.records[start:]) | {"prewarm_s": prewarm_s}
    L = [f"# Pre-warming the cache at startup (stretch): a cold-start user asks the top {args.n} questions\n",
         "| | User mean latency | User p95 latency | Cache hits | Startup work |", "|---|---:|---:|---:|---:|"]
    for label, r in rows.items():
        L.append(f"| {label} | {fmt_s(r['mean_s'])} | {fmt_s(r['p95_s'])} | {r['hits']}/{r['n']} | "
                 f"{r['prewarm_s']:.1f} s of LLM work |")
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["cold-warm", "workload", "prewarm"])
    p.add_argument("--n", type=int, default=None)
    p.add_argument("--requests", type=int, default=120)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    settings = get_settings()
    if not settings.cache_enabled:
        sys.exit("CACHE_ENABLED=false: nothing to benchmark")
    args.n = args.n or {"cold-warm": 20, "prewarm": 10}.get(args.mode, 0)
    report = {"cold-warm": cold_warm, "workload": workload, "prewarm": prewarm_mode}[args.mode](args, settings)
    print("\n" + report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
