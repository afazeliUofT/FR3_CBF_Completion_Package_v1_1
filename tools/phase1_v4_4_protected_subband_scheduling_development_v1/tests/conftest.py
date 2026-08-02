from __future__ import annotations

from pathlib import Path
import sys

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC = PACKAGE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def package_root() -> Path:
    return PACKAGE_ROOT
