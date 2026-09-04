"""
conftest.py — makes `pytest` work from the repository root.

Two things pytest cannot infer on its own:

1. `peak_preprocessor` is a directory of modules, not an installed package, so
   `test/test_pe_diversity.py` cannot import `pe_diversity` unless that directory
   is on sys.path. README.md documents the standalone invocation
   (`PYTHONPATH=peak_preprocessor python test/test_pe_diversity.py`); this file
   makes the bare `pytest` invocation work as well.

2. `test/test_onsset_install.py` is a standalone script, not a pytest module —
   it has no test_-prefixed functions and imports `onsset` at module level, so
   pytest errors during collection when OnSSET is not installed. It is excluded
   here and run directly, as its own docstring instructs.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "peak_preprocessor", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

collect_ignore = ["test/test_onsset_install.py"]
