#!/usr/bin/env python3
"""Freeze the exact world-to-local incumbent steering direction for 57 sectors.

The frozen scalar element-pattern table defines
``horizontal_offset_deg = target_geographic_azimuth - sector_azimuth`` and
``vertical_offset_deg = target_elevation - boresight_elevation``.  Sionna's
antenna positions are in each BS's local panel frame, so these offsets cannot
be inserted directly as local spherical angles.  This audit uses the
TR 38.901 z-y-x rotation matrix and exports the exact local unit vector.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def wrap_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def rotation_matrix(alpha: float, beta: float, gamma: float = 0.0) -> np.ndarray:
    """TR 38.901 (7.1-4): local-to-world z-y-x rotation matrix."""
    sa, ca = math.sin(alpha), math.cos(alpha)
    sb, cb = math.sin(beta), math.cos(beta)
    sg, cg = math.sin(gamma), math.cos(gamma)
    return np.array(
        [
            [ca * cb, ca * sb * sg - sa * cg, ca * sb * cg + sa * sg],
            [sa * cb, sa * sb * sg + ca * cg, sa * sb * cg - ca * sg],
            [-sb, cb * sg, cb * cg],
        ],
        dtype=np.float64,
    )


def geographic_unit_vector(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    """World vector for x=east, y=north, z=up and north-clockwise azimuth."""
    az = math.radians(float(azimuth_deg))
    el = math.radians(float(elevation_deg))
    return np.array(
        [math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)],
        dtype=np.float64,
    )


def local_direction(
    sector_azimuth_deg: float,
    downtilt_deg: float,
    horizontal_offset_deg: float,
    vertical_offset_deg: float,
) -> tuple[np.ndarray, dict[str, float]]:
    """Return the exact Sionna-local target direction and diagnostics."""
    target_azimuth_deg = (sector_azimuth_deg + horizontal_offset_deg) % 360.0
    boresight_elevation_deg = -float(downtilt_deg)
    target_elevation_deg = boresight_elevation_deg + vertical_offset_deg

    # Sionna local +x is boresight. Its orientation uses alpha about world z,
    # beta about intermediate y, and gamma about final x. With x=east/y=north,
    # alpha=90deg-geographic azimuth and positive beta is downtilt.
    alpha = math.radians((90.0 - sector_azimuth_deg) % 360.0)
    beta = math.radians(float(downtilt_deg))
    transform = rotation_matrix(alpha, beta, 0.0)
    target_world = geographic_unit_vector(target_azimuth_deg, target_elevation_deg)
    target_local = transform.T @ target_world
    target_local /= np.linalg.norm(target_local)
    reconstructed = transform @ target_local

    local_azimuth_deg = math.degrees(math.atan2(target_local[1], target_local[0]))
    local_elevation_deg = math.degrees(math.asin(np.clip(target_local[2], -1.0, 1.0)))
    wrong_direct = np.array(
        [
            math.cos(math.radians(vertical_offset_deg)) * math.cos(math.radians(horizontal_offset_deg)),
            math.cos(math.radians(vertical_offset_deg)) * math.sin(math.radians(horizontal_offset_deg)),
            math.sin(math.radians(vertical_offset_deg)),
        ]
    )
    corrected_small_angle = np.array(
        [
            math.cos(math.radians(vertical_offset_deg)) * math.cos(math.radians(-horizontal_offset_deg)),
            math.cos(math.radians(vertical_offset_deg)) * math.sin(math.radians(-horizontal_offset_deg)),
            math.sin(math.radians(vertical_offset_deg)),
        ]
    )
    wrong_angle = math.degrees(
        math.acos(np.clip(float(np.dot(wrong_direct, target_local)), -1.0, 1.0))
    )
    approximate_angle = math.degrees(
        math.acos(np.clip(float(np.dot(corrected_small_angle, target_local)), -1.0, 1.0))
    )
    diagnostics = {
        "target_geographic_azimuth_deg": target_azimuth_deg,
        "boresight_geographic_elevation_deg": boresight_elevation_deg,
        "target_geographic_elevation_deg": target_elevation_deg,
        "sionna_alpha_rad": alpha,
        "sionna_beta_rad": beta,
        "sionna_gamma_rad": 0.0,
        "local_azimuth_deg": local_azimuth_deg,
        "local_elevation_deg": local_elevation_deg,
        "world_reconstruction_error": float(np.linalg.norm(reconstructed - target_world)),
        "prior_direct_offset_direction_error_deg": wrong_angle,
        "signed_offset_approximation_error_deg": approximate_angle,
    }
    return target_local, diagnostics


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/tr38901_narval_dlp_pilot_prep.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    work = ROOT / cfg["outputs"]["work_dir"]
    work.mkdir(parents=True, exist_ok=True)

    sectors = pd.read_csv(ROOT / cfg["inputs"]["bs_sectors"])
    static = pd.read_csv(ROOT / cfg["inputs"]["sector_static"])
    static = static.loc[
        np.isclose(static["p452_time_percentage"], float(cfg["pilot"]["p452_time_percentage"]))
        & (static["polarization_label"] == str(cfg["pilot"]["p452_polarization"]))
        & (static["bs_gain_case"] == "ELEMENT_PATTERN_REFERENCE")
    ].drop_duplicates("sector_id")
    if len(sectors) != 57 or sectors["sector_id"].nunique() != 57:
        raise ValueError("Expected 57 unique frozen sectors")
    if len(static) != 57 or static["sector_id"].nunique() != 57:
        raise ValueError("Expected 57 static element-reference rows")

    merged = sectors[["sector_id", "site_id", "azimuth_deg", "downtilt_deg"]].merge(
        static[[
            "sector_id", "horizontal_offset_deg", "vertical_offset_deg",
            "element_pattern_gain_dbi", "basic_transmission_loss_db",
        ]],
        on="sector_id",
        validate="one_to_one",
    ).sort_values("sector_id").reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for record in merged.itertuples(index=False):
        vector, diagnostics = local_direction(
            float(record.azimuth_deg),
            float(record.downtilt_deg),
            float(record.horizontal_offset_deg),
            float(record.vertical_offset_deg),
        )
        rows.append(
            {
                "sector_id": str(record.sector_id),
                "site_id": str(record.site_id),
                "sector_geographic_azimuth_deg": float(record.azimuth_deg),
                "mechanical_downtilt_deg": float(record.downtilt_deg),
                "horizontal_offset_target_minus_sector_deg": float(record.horizontal_offset_deg),
                "vertical_offset_target_minus_boresight_deg": float(record.vertical_offset_deg),
                "local_direction_x": float(vector[0]),
                "local_direction_y": float(vector[1]),
                "local_direction_z": float(vector[2]),
                "element_pattern_gain_dbi": float(record.element_pattern_gain_dbi),
                "basic_transmission_loss_db": float(record.basic_transmission_loss_db),
                **diagnostics,
            }
        )

    frame = pd.DataFrame(rows)
    output_csv = work / "SIONNA_INCUMBENT_LOCAL_FRAME.csv"
    frame.to_csv(output_csv, index=False)
    norms = np.linalg.norm(
        frame[["local_direction_x", "local_direction_y", "local_direction_z"]].to_numpy(float),
        axis=1,
    )
    maximum_reconstruction_error = float(frame["world_reconstruction_error"].max())
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1e-12):
        raise ValueError("A local direction is not unit norm")
    if maximum_reconstruction_error > 2e-12:
        raise ValueError(f"World/local reconstruction failed: {maximum_reconstruction_error}")

    maximum_prior_error = float(frame["prior_direct_offset_direction_error_deg"].max())
    if maximum_prior_error < 1e-3:
        raise ValueError("The audit did not expose the expected direct-offset frame mismatch")

    decision = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_EXACT_SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT",
        "claim_boundary": cfg["claim_boundary"]["steering_frame"],
        "coordinate_conventions": {
            "world": "x=east, y=north, z=up; geographic azimuth north-clockwise",
            "sionna_local": "x=boresight, local y-z panel plane",
            "orientation": "TR 38.901 R=Rz(alpha)Ry(beta)Rx(gamma)",
            "alpha": "90 degrees minus sector geographic azimuth",
            "beta": "positive mechanical downtilt",
            "gamma": 0.0,
        },
        "source_offset_definition": {
            "horizontal": "target geographic azimuth minus sector geographic azimuth",
            "vertical": "target geographic elevation minus boresight elevation",
        },
        "finding": (
            "The superseded bundle inserted the signed geographic horizontal offset "
            "directly as a Sionna-local azimuth. For zero pitch the correct local "
            "azimuth has the opposite sign; with downtilt the exact R^T transform is required. "
            "The superseded GPU source also used exp(+j k r dot d) as a in "
            "||a^H W||, whereas Sionna's transmit row uses exp(+j k r dot d); "
            "therefore a must use exp(-j k r dot d)."
        ),
        "superseded_bundle": {
            "sha256": "a6ad7c3e202b57ff002b330b1d2c4e0f5b58a90b10fb7e64d6ae86c7069bef69",
            "disposition": "DO_NOT_RUN_SUPERSEDED_STEERING_FRAME",
        },
        "sector_count": len(frame),
        "maximum_world_reconstruction_error": maximum_reconstruction_error,
        "maximum_prior_direct_offset_direction_error_deg": maximum_prior_error,
        "maximum_signed_offset_approximation_error_deg": float(
            frame["signed_offset_approximation_error_deg"].max()
        ),
        "minimum_local_x_component": float(frame["local_direction_x"].min()),
        "maximum_local_x_component": float(frame["local_direction_x"].max()),
        "gpu_rule": (
            "The Narval pilot loads the frozen local unit vector by sector_id, "
            "does not reconstruct it from horizontal_offset_deg at runtime, and "
            "uses a=exp(-j k r_local dot d_local) so a^H matches Sionna's "
            "transmit channel-row spatial phase."
        ),
        "polarization_bound": cfg["pilot"]["transmit_polarization_bound"],
        "next_gate": "REBUILD_STEERING_HARDENED_NARVAL_BUNDLE",
    }
    write_json(work / "SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.json", decision)
    (work / "SIONNA_INCUMBENT_LOCAL_FRAME_AUDIT.md").write_text(
        "# Exact Sionna incumbent local-frame audit\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Sectors: `{len(frame)}`\n"
        f"- Maximum world reconstruction error: `{maximum_reconstruction_error:.3e}`\n"
        f"- Maximum error of the superseded direct-offset direction: `{maximum_prior_error:.6f}` deg\n"
        "- Superseded bundle: `a6ad7c3...bef69` — **do not run**\n\n"
        "The rebuilt GPU bundle loads exact frozen local unit vectors and uses "
        "the Hermitian steering-column phase exp(-j k r dot d). The two "
        "orthogonal Sionna polarization-group leakage powers are summed as a "
        "conservative total-polarized-power bound; this is not an exact H-field model.\n",
        encoding="utf-8",
    )
    print("SIONNA INCUMBENT LOCAL-FRAME AUDIT: PASS")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
