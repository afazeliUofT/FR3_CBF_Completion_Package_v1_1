#!/usr/bin/env python3
"""Record and verify the installed Sionna 2.0.1 PanelArray API."""
from __future__ import annotations

import argparse
import importlib.metadata
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/tr38901_nibi_dlp_pilot_prep.json",
    )
    args = parser.parse_args()

    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    work = ROOT / cfg["outputs"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    from sionna.phy.channel.tr38901 import PanelArray

    signature = inspect.signature(PanelArray.__init__)
    parameters = list(signature.parameters)
    required_keywords = {
        "element_vertical_spacing",
        "element_horizontal_spacing",
    }
    obsolete_keywords = {
        "vertical_spacing",
        "horizontal_spacing",
    }

    if not required_keywords.issubset(parameters):
        raise RuntimeError(
            "Installed PanelArray API lacks required element-spacing "
            f"keywords: {sorted(required_keywords - set(parameters))}"
        )
    if obsolete_keywords.intersection(parameters):
        raise RuntimeError(
            "Unexpected ambiguous PanelArray API exposes obsolete short "
            f"spacing keywords: {sorted(obsolete_keywords.intersection(parameters))}"
        )

    if importlib.metadata.version("sionna-no-rt") != str(
        expected["sionna_version"]
    ):
        raise RuntimeError("Unexpected Sionna distribution version")
    if importlib.metadata.version("torch").split("+", 1)[0] != str(
        expected["torch_base_version"]
    ):
        raise RuntimeError("Unexpected PyTorch base version")

    dual = PanelArray(
        num_rows_per_panel=int(expected["array_rows"]),
        num_cols_per_panel=int(expected["array_cols"]),
        polarization=str(expected["array_polarization"]),
        polarization_type=str(expected["array_polarization_type"]),
        antenna_pattern="38.901",
        carrier_frequency=float(expected["carrier_frequency_hz"]),
        element_vertical_spacing=0.5,
        element_horizontal_spacing=0.5,
        precision="double",
        device="cpu",
    )
    single = PanelArray(
        num_rows_per_panel=1,
        num_cols_per_panel=1,
        polarization="single",
        polarization_type="V",
        antenna_pattern="omni",
        carrier_frequency=float(expected["carrier_frequency_hz"]),
        element_vertical_spacing=0.5,
        element_horizontal_spacing=0.5,
        precision="single",
        device="cpu",
    )

    if int(dual.num_ant) != int(expected["array_port_count"]):
        raise RuntimeError(
            f"Unexpected dual-array port count: {dual.num_ant}"
        )
    if int(single.num_ant) != 1:
        raise RuntimeError(
            f"Unexpected single-polarized UT port count: {single.num_ant}"
        )

    vertical = float(dual.element_vertical_spacing.detach().cpu().item())
    horizontal = float(
        dual.element_horizontal_spacing.detach().cpu().item()
    )
    if not np.isclose(vertical, 0.5, rtol=0.0, atol=1e-12):
        raise RuntimeError(f"Unexpected vertical spacing: {vertical}")
    if not np.isclose(horizontal, 0.5, rtol=0.0, atol=1e-12):
        raise RuntimeError(f"Unexpected horizontal spacing: {horizontal}")

    record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_SIONNA_PANELARRAY_API_RECOVERY",
        "failure_diagnosis": (
            "The failed package passed vertical_spacing and "
            "horizontal_spacing to PanelArray. In Sionna 2.0.1 those names "
            "belong to AntennaArray; PanelArray requires "
            "element_vertical_spacing and element_horizontal_spacing."
        ),
        "environment": {
            "sionna_no_rt_version": importlib.metadata.version(
                "sionna-no-rt"
            ),
            "torch_version": importlib.metadata.version("torch"),
        },
        "panelarray_signature": str(signature),
        "panelarray_parameter_names": parameters,
        "verified_keywords": sorted(required_keywords),
        "dual_array": {
            "rows": int(expected["array_rows"]),
            "cols": int(expected["array_cols"]),
            "ports": int(dual.num_ant),
            "polarization": str(dual.polarization),
            "polarization_type": str(dual.polarization_type),
            "element_vertical_spacing_lambda": vertical,
            "element_horizontal_spacing_lambda": horizontal,
        },
        "ut_array": {
            "ports": int(single.num_ant),
            "polarization": str(single.polarization),
            "polarization_type": str(single.polarization_type),
        },
        "gpu_source_patch_verified": True,
        "next_gate": "SIONNA_DUAL_POLARIZATION_PORT_ORDER_AUDIT",
    }
    write_json(work / "SIONNA_PANELARRAY_API_RECOVERY.json", record)
    (work / "SIONNA_PANELARRAY_API_RECOVERY.md").write_text(
        "# Sionna PanelArray API recovery\n\n"
        f"- Status: `{record['status']}`\n"
        f"- Sionna: `{record['environment']['sionna_no_rt_version']}`\n"
        f"- PyTorch: `{record['environment']['torch_version']}`\n"
        "- Correct PanelArray keywords: "
        "`element_vertical_spacing`, `element_horizontal_spacing`\n"
        f"- Verified dual-array ports: `{dual.num_ant}`\n\n"
        "The same correction is applied to the future Nibi GPU pilot source, "
        "so the generated bundle cannot repeat the CPU port-audit failure.\n",
        encoding="utf-8",
    )

    print("SIONNA PANELARRAY API RECOVERY PROBE: PASS")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
