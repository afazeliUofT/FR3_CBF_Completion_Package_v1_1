from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "21_0_prepare_p452_pilot.py"

spec = importlib.util.spec_from_file_location("p452_pilot_prepare", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_accepts_full_tafl_roles() -> None:
    tx_role, rx_role = module.validate_tafl_endpoint_roles(
        pd.Series({"txrx": "TX"}),
        pd.Series({"txrx": "RX"}),
        "0000000001",
        "0000000002",
    )
    assert tx_role == "TX"
    assert rx_role == "RX"


@pytest.mark.parametrize(
    ("tx_value", "rx_value"),
    [("T", "R"), ("RX", "TX"), ("", "RX"), ("TX", "")],
)
def test_rejects_noncanonical_or_reversed_roles(
    tx_value: str,
    rx_value: str,
) -> None:
    with pytest.raises(ValueError, match="expected TX/RX roles"):
        module.validate_tafl_endpoint_roles(
            pd.Series({"txrx": tx_value}),
            pd.Series({"txrx": rx_value}),
            "tx-id",
            "rx-id",
        )
