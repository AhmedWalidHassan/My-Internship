"""The service's settings: the same typed object the capstone uses (one source of truth).

The definition lives in week1/common/settings.py because the capstone and the
provider helpers (common/utils.py) need it too. This module only makes `common`
importable from the repo-root `app` package and re-exports it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_WEEK1 = Path(__file__).resolve().parents[1] / "week1"
if str(_WEEK1) not in sys.path:
    sys.path.insert(0, str(_WEEK1))

from common.settings import Settings, get_settings  # noqa: E402

__all__ = ["Settings", "get_settings"]
