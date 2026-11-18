"""
Task 7 — publish the regression report: as THE eval-gate comment on a PR (updated in
place on every run, found by a hidden marker), or as an issue for a failed nightly.

    python post_report.py pr <number> regression_report.md
    python post_report.py issue "<title>" regression_report.md

Plain REST calls with GITHUB_TOKEN (stdlib only): the self-hosted runner image has no
`gh` CLI, and the job shouldn't install tools on it.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

MARKER = "<!-- northwind-eval-gate-report -->"


def api(method: str, path: str, body: dict | None = None):
    url = f"{os.environ.get('GITHUB_API_URL', 'https://api.github.com')}{path}"
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def main(argv: list[str]) -> int:
    kind, target, path = argv
    repo = os.environ["GITHUB_REPOSITORY"]
    body = f"{MARKER}\n{open(path, encoding='utf-8').read()}"
    if os.environ.get("GITHUB_SERVER_URL") and os.environ.get("GITHUB_RUN_ID"):
        body += (f"\n\n[Full run and artifacts]({os.environ['GITHUB_SERVER_URL']}/{repo}/actions/runs/"
                 f"{os.environ['GITHUB_RUN_ID']})")
    if kind == "pr":
        mine = [c for c in api("GET", f"/repos/{repo}/issues/{target}/comments?per_page=100")
                if MARKER in (c.get("body") or "")]
        if mine:
            api("PATCH", f"/repos/{repo}/issues/comments/{mine[-1]['id']}", {"body": body})
            print(f"updated comment {mine[-1]['html_url']}")
        else:
            print("posted", api("POST", f"/repos/{repo}/issues/{target}/comments", {"body": body})["html_url"])
    elif kind == "issue":
        print("opened", api("POST", f"/repos/{repo}/issues", {"title": target, "body": body})["html_url"])
    else:
        sys.exit(f"unknown kind {kind!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
