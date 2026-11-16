"""
From a request log line to its LangSmith trace, and how long that took.

    make find-trace RID=req-abc-123
    python week2/task_05_observability/scripts/find_trace.py <request_id | trace_id>

Every request log line carries three ways in, fastest first:
  1. `trace_url`: the direct link (when tracing is on). Click it: 0 seconds.
  2. `trace_id`: the LangSmith ROOT RUN id itself (the API passes it as run_id),
     so the trace is one lookup away, no search.
  3. `request_id`: also on the trace as metadata, so it can be searched for.
This script takes either id. With a request_id it searches the trace metadata
(the path you'd take from a load-balancer or client log that only has X-Request-ID).
"""

from __future__ import annotations

import re
import sys
import time
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
warnings.filterwarnings("ignore")

import app.config  # noqa: E402,F401  (week1 on sys.path)
import common.utils  # noqa: E402,F401  (loads week1/.env: the LangSmith key)
from langsmith import Client  # noqa: E402
from langsmith.utils import get_tracer_project  # noqa: E402

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    key = argv[0].strip()
    t0 = time.perf_counter()
    client = Client()
    project_name = get_tracer_project()
    if UUID_RE.match(key):
        run = client.read_run(key)
        how = "trace_id = root run id (direct read)"
    else:
        runs = list(client.list_runs(
            project_name=project_name, is_root=True, limit=1,
            filter=f'and(eq(metadata_key, "request_id"), eq(metadata_value, "{key}"))'))
        if not runs:
            print(f"no trace with metadata request_id={key!r} in project {project_name!r} "
                  f"(traces can take a few seconds to be ingested)")
            return 1
        run = runs[0]
        how = "request_id metadata search"
    project = client.read_project(project_name=project_name)
    host = getattr(client, "_host_url", None) or "https://smith.langchain.com"
    url = f"{host.rstrip('/')}/o/{project.tenant_id}/projects/p/{project.id}/r/{run.id}?poll=true"
    elapsed = time.perf_counter() - t0
    meta = (run.extra or {}).get("metadata", {})
    print(f"found in {elapsed:.2f} s via {how}")
    print(f"  run:        {run.name}  (root: {run.parent_run_id is None})  status: {run.status}")
    print(f"  trace_id:   {run.id}")
    print(f"  request_id: {meta.get('request_id')}   session_id: {meta.get('session_id')}")
    print(f"  started:    {run.start_time}")
    print(f"  url:        {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
