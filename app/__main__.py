"""`python -m app [--reload]` — start the API with host and port from the settings.

API_HOST / API_PORT come from the environment or week1/.env (see common/settings.py),
so `make run`, the container and a bare `python -m app` all start the same way.
"""

from __future__ import annotations

import sys

import uvicorn

from app.config import get_settings


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    s = get_settings()
    reload = "--reload" in argv
    uvicorn.run("app.main:app", host=s.api_host, port=s.api_port, reload=reload,
                reload_dirs=["app", "week1/common", "week1/capstone_internal_docs_assistant"] if reload else None,
                log_level=s.log_level.lower())


if __name__ == "__main__":
    main()
