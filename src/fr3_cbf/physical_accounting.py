"""Canonical physical-accounting helpers for the FR3 DLP-RZF work.

These helpers use exact local directions and the steering-column convention
compatible with a leakage expression of the form ``a.conj().T @ W``.
They are independent of the legacy scalar-angle synthetic prototype.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

C_M_S = 299_792_458.0


def rotation_matrix_zyx(
    yaw_rad: float,
    pitch_rad: float,
    roll_rad: float,
) -> np.ndarray:
    """Return the Sionna-style Z-Y-X orientation rotation matrix."""
    ca, sa = math.cos(yaw_rad), math.sin(yaw_rad)
    cb, sb = math.cos(pitch_rad), math.sin(pitch_rad)
    cg, sg = math.cos(roll_rad), math.sin(roll_rad)
    rz = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    ry = np.array([[cb, 0.0, sb], [0.0, 1.0, 0.0], [-sb, 0.0, cb]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cg, -sg], [0.0, sg, cg]])
    return rz @ ry @ rx


def normalize_direction(direction: np.ndarray) -> np.ndarray:
    value = np.asarray(direction, dtype=float).reshape(3)
    norm = float(np.linalg.norm(value))
    if norm <= 0 or not np.isfinite(norm):
        raise ValueError("direction must be finite and nonzero")
    return value / norm


def world_to_local_direction(
    world_direction: np.ndarray,
    yaw_rad: float,
    pitch_rad: float,
    roll_rad: float,
) -> np.ndarray:
    """Transform a world-frame unit direction into the local array frame."""
    world = normalize_direction(world_direction)
    rotation = rotation_matrix_zyx(yaw_rad, pitch_rad, roll_rad)
    local = rotation.T @ world
    return normalize_direction(local)


def steering_column_from_local_direction(
    antenna_positions_m: np.ndarray,
    local_direction: np.ndarray,
    carrier_frequency_hz: float,
    port_indices: Iterable[int] | None = None,
) -> np.ndarray:
    """Return ``exp(-j k d_m^T r_local)`` on selected ports.

    The negative phase is required when the leakage is evaluated as
    ``a.conj().T @ W`` while the transmit-array channel row uses the positive
    spatial phase convention.
    """
    positions = np.asarray(antenna_positions_m, dtype=float)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("antenna_positions_m must have shape [M,3]")
    if carrier_frequency_hz <= 0 or not np.isfinite(carrier_frequency_hz):
        raise ValueError("carrier_frequency_hz must be finite and positive")
    direction = normalize_direction(local_direction)
    phase = 2.0 * math.pi * carrier_frequency_hz / C_M_S * (
        positions @ direction
    )
    vector = np.zeros(positions.shape[0], dtype=np.complex128)
    if port_indices is None:
        vector[:] = np.exp(-1j * phase)
    else:
        indices = np.asarray(list(port_indices), dtype=np.int64)
        if indices.ndim != 1 or np.any(indices < 0) or np.any(
            indices >= positions.shape[0]
        ):
            raise ValueError("port_indices are invalid")
        vector[indices] = np.exp(-1j * phase[indices])
    return vector


def attenuation_db_to_amplitude_scale(q_db: np.ndarray | float) -> np.ndarray:
    q = np.asarray(q_db, dtype=float)
    if np.any(~np.isfinite(q)) or np.any(q < 0):
        raise ValueError("attenuation must be finite and nonnegative")
    return np.power(10.0, -q / 20.0)


def apply_mode_scales(
    amplitude_perpendicular: np.ndarray,
    amplitude_pol1: np.ndarray,
    amplitude_pol2: np.ndarray,
    scale_pol1: np.ndarray,
    scale_pol2: np.ndarray,
) -> np.ndarray:
    """Combine protected-tone amplitude components.

    Amplitude tensors have shape ``[U,B,K]`` and scale vectors have shape
    ``[B]``.
    """
    a0 = np.asarray(amplitude_perpendicular)
    a1 = np.asarray(amplitude_pol1)
    a2 = np.asarray(amplitude_pol2)
    if a0.shape != a1.shape or a0.shape != a2.shape or a0.ndim != 3:
        raise ValueError("amplitude tensors must share shape [U,B,K]")
    s1 = np.asarray(scale_pol1, dtype=float)
    s2 = np.asarray(scale_pol2, dtype=float)
    if s1.shape != (a0.shape[1],) or s2.shape != (a0.shape[1],):
        raise ValueError("scale vectors must have shape [B]")
    return a0 + s1[None, :, None] * a1 + s2[None, :, None] * a2


def user_rates_from_amplitudes(
    amplitudes: np.ndarray,
    serving_bs_index: np.ndarray,
    serving_stream_index: np.ndarray,
    noise_power_w: float,
) -> np.ndarray:
    """Compute full inter-cell user rates from ``[U,B,K]`` amplitudes."""
    value = np.asarray(amplitudes)
    if value.ndim != 3:
        raise ValueError("amplitudes must have shape [U,B,K]")
    users = value.shape[0]
    serving_bs = np.asarray(serving_bs_index, dtype=np.int64)
    serving_stream = np.asarray(serving_stream_index, dtype=np.int64)
    if serving_bs.shape != (users,) or serving_stream.shape != (users,):
        raise ValueError("serving index arrays must have shape [U]")
    if noise_power_w <= 0 or not np.isfinite(noise_power_w):
        raise ValueError("noise_power_w must be finite and positive")
    if np.any(serving_bs < 0) or np.any(serving_bs >= value.shape[1]):
        raise ValueError("serving_bs_index is invalid")
    if np.any(serving_stream < 0) or np.any(
        serving_stream >= value.shape[2]
    ):
        raise ValueError("serving_stream_index is invalid")
    power = np.abs(value) ** 2
    total = power.sum(axis=(1, 2))
    desired = power[
        np.arange(users),
        serving_bs,
        serving_stream,
    ]
    interference = total - desired
    sinr = desired / (interference + noise_power_w)
    return np.log2(1.0 + sinr)


def common_scale_oracle(
    nominal_received_mode_w: np.ndarray,
    aggregate_allowance_w: float,
) -> float:
    """Return the common amplitude scale used by the one-seed oracle pilot."""
    nominal = np.asarray(nominal_received_mode_w, dtype=float)
    if np.any(~np.isfinite(nominal)) or np.any(nominal < 0):
        raise ValueError("nominal received contributions are invalid")
    if aggregate_allowance_w < 0 or not np.isfinite(aggregate_allowance_w):
        raise ValueError("aggregate_allowance_w is invalid")
    total = float(nominal.sum())
    if total <= 0:
        return 1.0
    return min(1.0, math.sqrt(aggregate_allowance_w / total))
