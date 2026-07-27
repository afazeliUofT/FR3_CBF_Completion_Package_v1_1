"""Distributed local precoding and certified leakage-budget primitives.

The main operational architecture is intentionally not network-wide WMMSE.
Each BS uses only local UE CSI, its local incumbent steering vector, and one
scalar received-interference budget.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LeakageProjectionResult:
    precoder: np.ndarray
    nominal_leakage_w: float
    safe_leakage_w: float
    projection_scale: float
    power_before_w: float
    power_after_w: float
    active: bool


def upa_steering_vector(
    rows: int,
    cols: int,
    horizontal_offset_deg: float,
    vertical_offset_deg: float,
    spacing_lambda: float = 0.5,
    normalize: bool = False,
) -> np.ndarray:
    """Return a separable UPA steering vector in a local sector frame.

    Entries have unit magnitude by default, so coherent alignment provides an
    array factor of ``rows*cols`` relative to an isotropic element. Set
    ``normalize=True`` only for unit-norm algebraic tests.
    """
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if spacing_lambda <= 0:
        raise ValueError("spacing_lambda must be positive")
    az = np.radians(float(horizontal_offset_deg))
    el = np.radians(float(vertical_offset_deg))
    row_index = np.arange(rows, dtype=float)[:, None]
    col_index = np.arange(cols, dtype=float)[None, :]
    phase = 2.0 * np.pi * spacing_lambda * (
        col_index * np.sin(az) * np.cos(el) + row_index * np.sin(el)
    )
    vector = np.exp(1j * phase).reshape(rows * cols)
    if normalize:
        vector = vector / np.linalg.norm(vector)
    return vector.astype(np.complex128, copy=False)


def local_rzf_precoder(
    channels: np.ndarray,
    power_limit_w: float,
    regularization: float,
) -> np.ndarray:
    """Compute a local RZF precoder using only one BS's UE channels.

    ``channels`` has shape ``[M,K]`` with one column per locally served user.
    The returned matrix has shape ``[M,K]`` and exact Frobenius power
    ``power_limit_w`` unless the unnormalised RZF solution is zero.
    """
    h = np.asarray(channels, dtype=np.complex128)
    if h.ndim != 2 or h.shape[0] == 0 or h.shape[1] == 0:
        raise ValueError("channels must have nonempty shape [M,K]")
    if not np.all(np.isfinite(h)):
        raise ValueError("channels contain NaN or infinite values")
    if power_limit_w <= 0 or not np.isfinite(power_limit_w):
        raise ValueError("power_limit_w must be finite and positive")
    if regularization <= 0 or not np.isfinite(regularization):
        raise ValueError("regularization must be finite and positive")

    users = h.shape[1]
    gram = h.conj().T @ h + regularization * np.eye(users)
    v = h @ np.linalg.solve(gram, np.eye(users))
    norm_sq = float(np.vdot(v, v).real)
    if norm_sq <= 0:
        raise ValueError("RZF produced a zero precoder")
    return v * np.sqrt(power_limit_w / norm_sq)


def leakage_power_w(precoder: np.ndarray, steering: np.ndarray) -> float:
    """Return ``||a^H W||_2^2`` in watts when ``||W||_F^2`` is in watts."""
    w = np.asarray(precoder, dtype=np.complex128)
    a = np.asarray(steering, dtype=np.complex128).reshape(-1)
    if w.ndim != 2 or w.shape[0] != a.size:
        raise ValueError("precoder/steering dimensions do not match")
    if np.linalg.norm(a) == 0:
        raise ValueError("steering vector must be nonzero")
    value = a.conj() @ w
    return float(np.vdot(value, value).real)


def project_precoder_to_leakage_budget(
    nominal_precoder: np.ndarray,
    steering: np.ndarray,
    maximum_leakage_w: float,
    tolerance: float = 1e-12,
) -> LeakageProjectionResult:
    """Exact minimum-Frobenius local projection onto one leakage constraint.

    Let ``u=a/||a||`` and decompose ``W0=W_perp+W_parallel`` with
    ``W_parallel=u u^H W0``. If the leakage budget is active, the unique
    Euclidean projection is

    ``W_safe = W_perp + s W_parallel``,

    where ``s=sqrt(maximum_leakage/current_leakage)``.

    The projection never increases transmit power and requires no inter-BS CSI
    or iterative network-wide optimization.
    """
    w0 = np.asarray(nominal_precoder, dtype=np.complex128)
    a = np.asarray(steering, dtype=np.complex128).reshape(-1)
    if w0.ndim != 2 or w0.shape[0] != a.size:
        raise ValueError("nominal_precoder/steering dimensions do not match")
    if maximum_leakage_w < 0 or not np.isfinite(maximum_leakage_w):
        raise ValueError("maximum_leakage_w must be finite and nonnegative")
    a_norm = float(np.linalg.norm(a))
    if a_norm <= 0:
        raise ValueError("steering vector must be nonzero")

    nominal = leakage_power_w(w0, a)
    power_before = float(np.vdot(w0, w0).real)
    comparison_scale = max(
        nominal, maximum_leakage_w, np.finfo(float).tiny
    )
    if nominal <= maximum_leakage_w + tolerance * comparison_scale:
        return LeakageProjectionResult(
            precoder=w0.copy(),
            nominal_leakage_w=nominal,
            safe_leakage_w=nominal,
            projection_scale=1.0,
            power_before_w=power_before,
            power_after_w=power_before,
            active=False,
        )

    unit = a / a_norm
    coefficient = unit.conj() @ w0
    parallel = np.outer(unit, coefficient)
    scale = float(np.sqrt(maximum_leakage_w / nominal))
    safe = w0 - (1.0 - scale) * parallel
    safe_leakage = leakage_power_w(safe, a)
    power_after = float(np.vdot(safe, safe).real)

    absolute_tolerance = tolerance * comparison_scale
    if safe_leakage > maximum_leakage_w + absolute_tolerance:
        raise RuntimeError(
            "leakage projection failed: "
            f"{safe_leakage} > {maximum_leakage_w}"
        )
    if power_after > power_before + max(tolerance, tolerance * power_before):
        raise RuntimeError("leakage projection increased transmit power")

    return LeakageProjectionResult(
        precoder=safe,
        nominal_leakage_w=nominal,
        safe_leakage_w=safe_leakage,
        projection_scale=scale,
        power_before_w=power_before,
        power_after_w=power_after,
        active=True,
    )


def proportional_received_interference_budgets(
    nominal_received_interference_w: np.ndarray,
    aggregate_threshold_w: float,
    reserve_fraction: float,
) -> np.ndarray:
    """Allocate certified nonnegative local budgets from scalar leakage reports."""
    nominal = np.asarray(nominal_received_interference_w, dtype=float)
    if nominal.ndim != 1 or nominal.size == 0:
        raise ValueError("nominal_received_interference_w must be a nonempty vector")
    if np.any(~np.isfinite(nominal)) or np.any(nominal < 0):
        raise ValueError("nominal received interference must be finite and nonnegative")
    if aggregate_threshold_w <= 0 or not np.isfinite(aggregate_threshold_w):
        raise ValueError("aggregate_threshold_w must be finite and positive")
    if not 0 <= reserve_fraction < 1:
        raise ValueError("reserve_fraction must be in [0,1)")

    allowance = (1.0 - reserve_fraction) * aggregate_threshold_w
    total = float(nominal.sum())
    if total > 0:
        budgets = allowance * nominal / total
    else:
        budgets = np.full(nominal.size, allowance / nominal.size)
    # Force exact certified sum up to floating arithmetic.
    budgets[-1] += allowance - float(budgets.sum())
    if np.any(budgets < -1e-30):
        raise RuntimeError("budget allocator produced a negative budget")
    return np.maximum(budgets, 0.0)


def local_sum_rate_bps_hz(
    channels: np.ndarray,
    precoder: np.ndarray,
    noise_power_w: float,
) -> float:
    """Return local sum rate with intra-cell interference and no inter-cell term."""
    h = np.asarray(channels, dtype=np.complex128)
    w = np.asarray(precoder, dtype=np.complex128)
    if h.shape != w.shape or h.ndim != 2:
        raise ValueError("channels and precoder must have matching [M,K] shape")
    if noise_power_w <= 0 or not np.isfinite(noise_power_w):
        raise ValueError("noise_power_w must be finite and positive")
    effective = h.conj().T @ w
    power = np.abs(effective) ** 2
    desired = np.diag(power)
    interference = power.sum(axis=1) - desired
    sinr = desired / (interference + noise_power_w)
    return float(np.log2(1.0 + sinr).sum())
