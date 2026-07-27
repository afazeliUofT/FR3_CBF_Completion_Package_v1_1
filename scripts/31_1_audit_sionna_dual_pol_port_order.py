#!/usr/bin/env python3
"""Audit exact Sionna 2.0.1 dual-polarized port ordering and steering bases."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
C_M_S = 299_792_458.0


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def steering_basis(
    positions_m: np.ndarray,
    indices: np.ndarray,
    carrier_hz: float,
    horizontal_offset_deg: float,
    vertical_offset_deg: float,
) -> np.ndarray:
    az = math.radians(horizontal_offset_deg)
    el = math.radians(vertical_offset_deg)
    direction = np.array(
        [math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)],
        dtype=np.float64,
    )
    phase = 2.0 * math.pi * carrier_hz / C_M_S * (positions_m @ direction)
    vector = np.zeros(positions_m.shape[0], dtype=np.complex128)
    vector[indices] = np.exp(-1j * phase[indices])
    return vector


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="config/tr38901_narval_dlp_pilot_prep.json"
    )
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    expected = cfg["expected"]
    work = ROOT / cfg["outputs"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    from sionna.phy.channel.tr38901 import PanelArray

    if importlib.metadata.version("sionna-no-rt") != expected["sionna_version"]:
        raise ValueError("Unexpected Sionna version")
    if importlib.metadata.version("torch").split("+", 1)[0] != expected[
        "torch_base_version"
    ]:
        raise ValueError("Unexpected PyTorch version")

    carrier = float(expected["carrier_frequency_hz"])
    array = PanelArray(
        num_rows_per_panel=int(expected["array_rows"]),
        num_cols_per_panel=int(expected["array_cols"]),
        polarization=str(expected["array_polarization"]),
        polarization_type=str(expected["array_polarization_type"]),
        antenna_pattern="38.901",
        carrier_frequency=carrier,
        element_vertical_spacing=0.5,
        element_horizontal_spacing=0.5,
        precision="double",
        device="cpu",
    )
    positions = array.ant_pos.detach().cpu().numpy().astype(np.float64)
    pol1 = array.ant_ind_pol1.detach().cpu().numpy().astype(np.int64)
    pol2 = array.ant_ind_pol2.detach().cpu().numpy().astype(np.int64)

    ports = int(expected["array_port_count"])
    if array.num_ant != ports or positions.shape != (ports, 3):
        raise ValueError("Unexpected Sionna port count/position shape")
    if len(pol1) != ports // 2 or len(pol2) != ports // 2:
        raise ValueError("Unexpected polarization index counts")
    if set(pol1).intersection(set(pol2)):
        raise ValueError("Polarization index sets overlap")
    if sorted(np.concatenate([pol1, pol2]).tolist()) != list(range(ports)):
        raise ValueError("Polarization index sets do not cover all ports")

    pol1_positions = positions[pol1]
    pol2_positions = positions[pol2]
    order1 = np.lexsort((pol1_positions[:, 2], pol1_positions[:, 1], pol1_positions[:, 0]))
    order2 = np.lexsort((pol2_positions[:, 2], pol2_positions[:, 1], pol2_positions[:, 0]))
    duplicate_error = float(
        np.max(np.abs(pol1_positions[order1] - pol2_positions[order2]))
    )
    if duplicate_error > 1e-12:
        raise ValueError("Dual-polarization position sets are not duplicated")

    wavelength = C_M_S / carrier
    y_unique = np.unique(np.round(positions[:, 1], 12))
    z_unique = np.unique(np.round(positions[:, 2], 12))
    y_spacing = np.diff(y_unique)
    z_spacing = np.diff(z_unique)
    expected_spacing = 0.5 * wavelength
    if not np.allclose(y_spacing, expected_spacing, rtol=0, atol=1e-10):
        raise ValueError("Unexpected horizontal spacing")
    if not np.allclose(z_spacing, expected_spacing, rtol=0, atol=1e-10):
        raise ValueError("Unexpected vertical spacing")
    if not np.allclose(positions[:, 0], 0.0, atol=1e-12):
        raise ValueError("Sionna panel positions are not on the local y-z plane")

    a1 = steering_basis(positions, pol1, carrier, 17.0, 9.0)
    a2 = steering_basis(positions, pol2, carrier, 17.0, 9.0)
    orthogonality = abs(np.vdot(a1, a2))
    if orthogonality > 1e-12:
        raise ValueError("Polarization steering modes are not orthogonal")
    if abs(np.vdot(a1, a1).real - len(pol1)) > 1e-10:
        raise ValueError("Unexpected polarization-1 steering norm")
    if abs(np.vdot(a2, a2).real - len(pol2)) > 1e-10:
        raise ValueError("Unexpected polarization-2 steering norm")

    port_path = work / "SIONNA_8X8_DUAL_PORT_ORDER.csv"
    with port_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["port_index", "polarization", "x_m", "y_m", "z_m"])
        pol1_set = set(pol1.tolist())
        for index, position in enumerate(positions):
            writer.writerow(
                [
                    index,
                    "pol1" if index in pol1_set else "pol2",
                    float(position[0]),
                    float(position[1]),
                    float(position[2]),
                ]
            )

    np.savez_compressed(
        work / "SIONNA_8X8_DUAL_STEERING_SAMPLE.npz",
        positions_m=positions,
        ant_ind_pol1=pol1,
        ant_ind_pol2=pol2,
        steering_pol1=a1,
        steering_pol2=a2,
    )
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_SIONNA_DUAL_POLARIZATION_PORT_ORDER_AND_BASIS",
        "claim_boundary": cfg["claim_boundary"]["port_audit"],
        "environment": {
            "sionna_version": importlib.metadata.version("sionna-no-rt"),
            "torch_version": importlib.metadata.version("torch"),
            "device": "cpu",
        },
        "array": {
            "rows": expected["array_rows"],
            "cols": expected["array_cols"],
            "polarization": expected["array_polarization"],
            "polarization_type": expected["array_polarization_type"],
            "ports": ports,
            "ports_per_polarization": len(pol1),
            "wavelength_m": wavelength,
            "horizontal_spacing_m": float(y_spacing[0]),
            "vertical_spacing_m": float(z_spacing[0]),
            "position_duplicate_error_m": duplicate_error,
            "polarization_mode_inner_product": float(orthogonality),
        },
        "ordering": {
            "ant_ind_pol1": pol1.tolist(),
            "ant_ind_pol2": pol2.tolist(),
            "positions_sha256": digest(positions),
            "steering_pol1_sha256": digest(a1),
            "steering_pol2_sha256": digest(a2),
        },
        "steering_vector_convention": (
            "a=exp(-j k r_local dot d_local), so a^H equals the Sionna "
            "transmit channel-row spatial phase exp(+j k r_local dot d_local)."
        ),
        "pilot_safety_rule": (
            "The protected-tone transmit-domain leakage allowance is divided "
            "between the two orthogonal Sionna polarization port groups in "
            "proportion to their nominal mode leakage; each mode is projected "
            "locally and their received powers are summed."
        ),
        "next_gate": "BUILD_REVIEWABLE_NARVAL_GPU_PILOT_BUNDLE",
    }
    write_json(work / "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.json", audit)
    (work / "SIONNA_DUAL_POL_PORT_ORDER_AUDIT.md").write_text(
        "# Sionna dual-polarized port-order audit\n\n"
        f"- Status: `{audit['status']}`\n"
        f"- Ports: `{ports}`\n"
        f"- Ports per polarization: `{len(pol1)}`\n"
        f"- Position duplication error: `{duplicate_error:.3e}` m\n"
        f"- Polarization-mode inner product: `{orthogonality:.3e}`\n\n"
        "The GPU pilot must use the exported `ant_ind_pol1` and `ant_ind_pol2` "
        "sets rather than assuming alternating port order.\n",
        encoding="utf-8",
    )
    print("SIONNA DUAL-POLARIZATION PORT ORDER AUDIT: PASS")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
