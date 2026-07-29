"""Local dynamic-readiness helpers for the validated full-topology export.

The routines in this module are deliberately labelled as screening tools.
They do not constitute the final distributed controller or a paper result.
"""
from __future__ import annotations

import math

import numpy as np


def required_common_attenuation_db(
    nominal_interference_w: np.ndarray,
    allowance_w: np.ndarray,
) -> np.ndarray:
    """Return the common power-attenuation requirement in dB."""
    nominal = np.asarray(nominal_interference_w, dtype=float)
    allowance = np.asarray(allowance_w, dtype=float)
    if nominal.shape != allowance.shape:
        raise ValueError("nominal and allowance arrays must share a shape")
    if np.any(~np.isfinite(nominal)) or np.any(nominal < 0):
        raise ValueError("nominal interference must be finite and nonnegative")
    if np.any(~np.isfinite(allowance)) or np.any(allowance <= 0):
        raise ValueError("allowance must be finite and positive")
    return np.maximum(
        0.0,
        10.0 * np.log10(np.maximum(nominal, 1e-300) / allowance),
    )


def interval_maximum(values: np.ndarray, interval: int) -> np.ndarray:
    """Take the maximum one-second requirement in each update interval."""
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or interval <= 0:
        raise ValueError("values must be 1-D and interval must be positive")
    return np.asarray(
        [
            float(np.max(x[start : min(start + interval, len(x))]))
            for start in range(0, len(x), interval)
        ],
        dtype=float,
    )


def expand_interval_values(
    values: np.ndarray,
    interval: int,
    length: int,
) -> np.ndarray:
    value = np.repeat(np.asarray(values, dtype=float), interval)
    return value[:length]


def simulate_myopic_common_command(
    required_db: np.ndarray,
    update_interval_s: int,
    delay_intervals: int,
    slew_db_per_update: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simulate a current-state command with delay and an absolute slew limit.

    The initial applied command is the first required value. At each update,
    the command targets the current interval requirement and is clipped to the
    previous command plus/minus the declared slew limit. It applies after the
    declared integer number of update intervals.
    """
    if delay_intervals < 0 or slew_db_per_update <= 0:
        raise ValueError("delay must be nonnegative and slew must be positive")
    bucket = interval_maximum(required_db, update_interval_s)
    command = np.empty_like(bucket)
    command[0] = bucket[0]
    for index in range(1, len(bucket)):
        command[index] = np.clip(
            bucket[index],
            command[index - 1] - slew_db_per_update,
            command[index - 1] + slew_db_per_update,
        )

    applied = np.full_like(bucket, command[0])
    for command_index, value in enumerate(command):
        applied_index = command_index + delay_intervals
        if applied_index < len(applied):
            applied[applied_index] = value

    return (
        bucket,
        command,
        expand_interval_values(
            applied,
            update_interval_s,
            len(required_db),
        ),
    )


def minimal_slew_majorant(
    interval_requirement_db: np.ndarray,
    slew_db_per_update: float,
) -> np.ndarray:
    """Return a minimal perfect-lookahead majorant under an absolute slew cap.

    This is an offline geometry-known reference, not the proposed practical
    controller. It shows whether a pre-ramped safe trajectory exists.
    """
    requirement = np.asarray(interval_requirement_db, dtype=float)
    if requirement.ndim != 1 or slew_db_per_update <= 0:
        raise ValueError("invalid requirement or slew")
    value = requirement.copy()
    for _ in range(4):
        for index in range(len(value) - 2, -1, -1):
            value[index] = max(
                value[index],
                value[index + 1] - slew_db_per_update,
            )
        for index in range(1, len(value)):
            value[index] = max(
                value[index],
                value[index - 1] - slew_db_per_update,
            )
    if np.any(value + 1e-12 < requirement):
        raise RuntimeError("majorant fell below the requirement")
    if len(value) > 1 and np.max(np.abs(np.diff(value))) > (
        slew_db_per_update + 1e-10
    ):
        raise RuntimeError("majorant violates the slew constraint")
    return value


def interference_ratio_from_attenuation_db(
    nominal_interference_w: np.ndarray,
    allowance_w: np.ndarray,
    attenuation_db: np.ndarray,
) -> np.ndarray:
    nominal = np.asarray(nominal_interference_w, dtype=float)
    allowance = np.asarray(allowance_w, dtype=float)
    attenuation = np.asarray(attenuation_db, dtype=float)
    if nominal.shape != allowance.shape or nominal.shape != attenuation.shape:
        raise ValueError("all arrays must share a shape")
    return nominal * np.power(10.0, -attenuation / 10.0) / allowance


def network_rates_for_common_attenuation(
    attenuation_db: np.ndarray,
    amp_perpendicular: np.ndarray,
    amp_pol1: np.ndarray,
    amp_pol2: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    other_weighted_rate: np.ndarray,
    protected_weight: float,
) -> np.ndarray:
    """Evaluate total weighted network rate for a common mode attenuation."""
    q = np.asarray(attenuation_db, dtype=float)
    a0 = np.asarray(amp_perpendicular)
    a1 = np.asarray(amp_pol1)
    a2 = np.asarray(amp_pol2)
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    other = np.asarray(other_weighted_rate, dtype=float)
    users = a0.shape[0]
    if a0.shape != a1.shape or a0.shape != a2.shape:
        raise ValueError("protected amplitude components must share a shape")
    if a0.ndim != 3 or a0.shape[1:] != (57, 4):
        raise ValueError("protected amplitude shape must be [U,57,4]")
    if serving.shape != (users,) or stream.shape != (users,):
        raise ValueError("serving arrays must have one entry per user")
    if other.shape != (users,):
        raise ValueError("other-frequency rates must have one entry per user")

    result = np.empty(len(q), dtype=float)
    for index, value in enumerate(q):
        scale = 10.0 ** (-float(value) / 20.0)
        amplitude = a0 + scale * a1 + scale * a2
        power = np.abs(amplitude) ** 2
        total = power.sum(axis=(1, 2))
        desired = power[
            np.arange(users),
            serving,
            stream,
        ]
        sinr = desired / (
            total - desired + float(protected_noise_w)
        )
        protected_rate = np.log2(1.0 + sinr)
        result[index] = float(
            np.sum(other + protected_weight * protected_rate)
        )
    return result


def weakest_mode_preservation_scales(
    received_mode_w: np.ndarray,
    allowance_w: float,
) -> np.ndarray:
    """A non-utility-aware static opportunity screen.

    The weakest modes are left at unit scale until the allowance is consumed;
    the next mode is partially scaled and all stronger modes are nulled. This
    is not a proposed controller. It only demonstrates whether nonuniform mode
    actions can differ from the common-scale reference.
    """
    contribution = np.asarray(received_mode_w, dtype=float)
    if contribution.shape != (57, 2):
        raise ValueError("received_mode_w must have shape [57,2]")
    if np.any(contribution < 0) or allowance_w <= 0:
        raise ValueError("invalid contribution or allowance")
    flat = contribution.reshape(-1)
    order = np.argsort(flat)
    scale = np.zeros_like(flat)
    remaining = float(allowance_w)
    for index in order:
        if flat[index] <= remaining:
            scale[index] = 1.0
            remaining -= float(flat[index])
        elif remaining > 0 and flat[index] > 0:
            scale[index] = math.sqrt(remaining / float(flat[index]))
            remaining = 0.0
            break
        else:
            break
    return scale.reshape(57, 2)


def user_rates_for_mode_scales(
    scale_pol1: np.ndarray,
    scale_pol2: np.ndarray,
    amp_perpendicular: np.ndarray,
    amp_pol1: np.ndarray,
    amp_pol2: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    other_weighted_rate: np.ndarray,
    protected_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return total weighted and protected-only user rates."""
    s1 = np.asarray(scale_pol1, dtype=float)
    s2 = np.asarray(scale_pol2, dtype=float)
    if s1.shape != (57,) or s2.shape != (57,):
        raise ValueError("mode scale vectors must have shape [57]")
    amplitude = (
        np.asarray(amp_perpendicular)
        + s1[None, :, None] * np.asarray(amp_pol1)
        + s2[None, :, None] * np.asarray(amp_pol2)
    )
    power = np.abs(amplitude) ** 2
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    desired = power[
        np.arange(len(serving)),
        serving,
        stream,
    ]
    total = power.sum(axis=(1, 2))
    protected_rate = np.log2(
        1.0
        + desired
        / (total - desired + float(protected_noise_w))
    )
    total_rate = (
        np.asarray(other_weighted_rate, dtype=float)
        + float(protected_weight) * protected_rate
    )
    return total_rate, protected_rate
