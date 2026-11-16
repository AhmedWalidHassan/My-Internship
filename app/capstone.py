"""The one place the service reaches into the Week 1 capstone.

The capstone is a single file that `streamlit run` executes as a script, so it is
not an importable package. It is loaded here from its path, once, and registered
in `sys.modules`, so the service and the test suite share the same module object
(monkeypatching it in a test affects the code the service runs).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPSTONE_PATH = REPO_ROOT / "week1" / "capstone_internal_docs_assistant" / "app.py"
MODULE_NAME = "capstone_app"


def load_capstone() -> ModuleType:
    """Import the capstone module (only the first call executes it)."""
    module = sys.modules.get(MODULE_NAME)
    if module is None:
        spec = importlib.util.spec_from_file_location(MODULE_NAME, CAPSTONE_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(MODULE_NAME, None)
            raise
    return module
