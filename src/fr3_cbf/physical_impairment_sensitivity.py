"""Practical null-depth and deterministic array/steering sensitivity tools.

These tools perform engineering sensitivity analysis. They do not convert
assumed perturbation levels into measured or probabilistically calibrated
uncertainty bounds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

C_M_S = 299_792_458.0


@dataclass(frozen=True)
class ModeMatrices:
    perpendicular: np.ndarray
    polarization_1: np.ndarray
    polarization_2: np.ndarray


def mode_matrices(
    protected_precoder: np.ndarray,
    steering_pol1: np.ndarray,
    steering_pol2: np.ndarray,
) -> ModeMatrices:
    w_all = np.asarray(protected_precoder)
    s1_all = np.asarray(steering_pol1)
    s2_all = np.asarray(steering_pol2)
    if w_all.shape != (57, 128, 4):
        raise ValueError("protected_precoder must have shape [57,128,4]")
    p0 = np.empty_like(w_all, dtype=np.complex128)
    p1 = np.empty_like(w_all, dtype=np.complex128)
    p2 = np.empty_like(w_all, dtype=np.complex128)
    for sector in range(57):
        w = w_all[sector].astype(np.complex128)
        u1 = s1_all[sector].astype(np.complex128)
        u2 = s2_all[sector].astype(np.complex128)
        u1 /= np.linalg.norm(u1)
        u2 /= np.linalg.norm(u2)
        value1 = u1[:, None] * (u1.conj() @ w)[None, :]
        value2 = u2[:, None] * (u2.conj() @ w)[None, :]
        p1[sector] = value1
        p2[sector] = value2
        p0[sector] = w - value1 - value2
    return ModeMatrices(p0, p1, p2)


def safe_precoder(matrices: ModeMatrices, q_db: np.ndarray) -> np.ndarray:
    q = np.asarray(q_db, dtype=float)
    if q.shape != (57, 2):
        raise ValueError("q_db must have shape [57,2]")
    scale = np.power(10.0, -q / 20.0)
    return (
        matrices.perpendicular
        + scale[:, 0, None, None] * matrices.polarization_1
        + scale[:, 1, None, None] * matrices.polarization_2
    )


def renormalize_sector_power(
    implemented: np.ndarray,
    reference: np.ndarray,
) -> np.ndarray:
    actual = np.sum(np.abs(implemented) ** 2, axis=(1, 2))
    target = np.sum(np.abs(reference) ** 2, axis=(1, 2))
    factor = np.ones(57, dtype=float)
    positive = actual > 0.0
    factor[positive] = np.sqrt(target[positive] / actual[positive])
    return implemented * factor[:, None, None]


def mode_leakage(
    precoder: np.ndarray,
    steering_pol1: np.ndarray,
    steering_pol2: np.ndarray,
) -> np.ndarray:
    w = np.asarray(precoder)
    s1 = np.asarray(steering_pol1)
    s2 = np.asarray(steering_pol2)
    c1 = np.einsum("bm,bmk->bk", s1.conj(), w, optimize=True)
    c2 = np.einsum("bm,bmk->bk", s2.conj(), w, optimize=True)
    return np.column_stack(
        [
            np.sum(np.abs(c1) ** 2, axis=1),
            np.sum(np.abs(c2) ** 2, axis=1),
        ]
    ).astype(np.float64)


def second_ratio_from_interval_leakage(
    kappa_time_sector: np.ndarray,
    interval_leakage_w: np.ndarray,
    update_interval_s: int,
    allowance_w: np.ndarray,
) -> np.ndarray:
    kappa = np.asarray(kappa_time_sector, dtype=float)
    leakage = np.asarray(interval_leakage_w, dtype=float)
    allowance = np.asarray(allowance_w, dtype=float)
    result = np.empty(len(kappa), dtype=float)
    for second in range(len(kappa)):
        interval = min(second // update_interval_s, len(leakage) - 1)
        result[second] = float(
            np.sum(kappa[second, :, None] * leakage[interval])
            / allowance[second]
        )
    return result


def required_uniform_backoff_db(maximum_ratio: float) -> float:
    if maximum_ratio <= 0 or not np.isfinite(maximum_ratio):
        raise ValueError("maximum_ratio must be finite and positive")
    return max(0.0, 10.0 * math.log10(maximum_ratio))


def steering_from_local_direction(
    positions_m: np.ndarray,
    local_direction: np.ndarray,
    frequency_hz: float,
    pol1_mask: np.ndarray,
    pol2_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    positions = np.asarray(positions_m, dtype=float)
    direction = np.asarray(local_direction, dtype=float)
    direction /= np.linalg.norm(direction)
    phase = 2.0 * math.pi * float(frequency_hz) / C_M_S * (
        positions @ direction
    )
    spatial = np.exp(-1j * phase)
    value1 = np.zeros(len(positions), dtype=np.complex128)
    value2 = np.zeros(len(positions), dtype=np.complex128)
    value1[np.asarray(pol1_mask, dtype=bool)] = spatial[
        np.asarray(pol1_mask, dtype=bool)
    ]
    value2[np.asarray(pol2_mask, dtype=bool)] = spatial[
        np.asarray(pol2_mask, dtype=bool)
    ]
    return value1, value2


def perturbed_direction(
    nominal: np.ndarray,
    error_deg: float,
    random_vector: np.ndarray,
) -> np.ndarray:
    direction = np.asarray(nominal, dtype=float)
    direction /= np.linalg.norm(direction)
    tangent = np.asarray(random_vector, dtype=float)
    tangent -= direction * float(np.dot(tangent, direction))
    norm = np.linalg.norm(tangent)
    if norm <= 1e-15:
        raise ValueError("random tangent direction is degenerate")
    tangent /= norm
    angle = math.radians(float(error_deg))
    result = math.cos(angle) * direction + math.sin(angle) * tangent
    return result / np.linalg.norm(result)


def quantize_precoder_phase(
    precoder: np.ndarray,
    bits: int,
) -> np.ndarray:
    if bits <= 0:
        raise ValueError("bits must be positive")
    value = np.asarray(precoder)
    levels = 2 ** int(bits)
    step = 2.0 * math.pi / levels
    phase = np.angle(value)
    quantized = np.round(phase / step) * step
    return np.abs(value) * np.exp(1j * quantized)


def correlated_port_errors(
    rng: np.random.Generator,
    polarization: np.ndarray,
    row_index: np.ndarray,
    col_index: np.ndarray,
    phase_rms_deg: float,
    gain_rms_db: float,
    model: str,
) -> np.ndarray:
    pol = np.asarray(polarization)
    row = np.asarray(row_index, dtype=int)
    col = np.asarray(col_index, dtype=int)
    result_phase = np.zeros((57, len(pol)), dtype=float)
    result_gain = np.zeros_like(result_phase)

    if model == "independent_port":
        result_phase = rng.normal(0.0, phase_rms_deg, result_phase.shape)
        result_gain = rng.normal(0.0, gain_rms_db, result_gain.shape)
    elif model in {"tile_2x2", "tile_4x4"}:
        tile = 2 if model == "tile_2x2" else 4
        for sector in range(57):
            for pol_name in np.unique(pol):
                mask_pol = pol == pol_name
                for tile_row in range(0, 8, tile):
                    for tile_col in range(0, 8, tile):
                        mask = (
                            mask_pol
                            & (row >= tile_row)
                            & (row < tile_row + tile)
                            & (col >= tile_col)
                            & (col < tile_col + tile)
                        )
                        result_phase[sector, mask] = rng.normal(
                            0.0, phase_rms_deg
                        )
                        result_gain[sector, mask] = rng.normal(
                            0.0, gain_rms_db
                        )
    elif model == "common_per_polarization":
        for sector in range(57):
            for pol_name in np.unique(pol):
                mask = pol == pol_name
                result_phase[sector, mask] = rng.normal(
                    0.0, phase_rms_deg
                )
                result_gain[sector, mask] = rng.normal(
                    0.0, gain_rms_db
                )
    else:
        raise ValueError(f"unknown correlation model: {model}")

    amplitude = np.power(10.0, result_gain / 20.0)
    return amplitude * np.exp(1j * np.deg2rad(result_phase))
