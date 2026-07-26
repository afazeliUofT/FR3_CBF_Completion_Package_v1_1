"""Import-path bootstrap for the FR3 CBF test suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in (
    ROOT / "src",
    ROOT / "scripts",
    ROOT,
):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
