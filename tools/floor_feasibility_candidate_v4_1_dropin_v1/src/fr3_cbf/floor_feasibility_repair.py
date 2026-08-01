"""Exact floor-feasibility oracles and a sparse lexicographic repair.

This module is a new candidate-v4.1 diagnostic/repair layer.  It does not modify
or replace the immutable reviewed phase-1 package.  The fixed mode commands are
held constant.  User-floor and long/short incumbent constraints are represented
exactly as linear inequalities in protected-subband stream-power scales.

The primary objective is feasibility of all hard constraints.  The secondary
objective is minimum weighted L1 deviation from the reviewed fallback action;
sum rate is never used as the primary objective.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import csr_matrix, eye as sparse_eye, hstack, vstack


FLOOR_COMPARISON_TOLERANCE = 1e-12
EESS_VERIFICATION_TOLERANCE = 1e-10


@dataclass(frozen=True)
class LinearSystem:
    """A labelled system ``A x <= b``."""

    a_ub: np.ndarray
    b_ub: np.ndarray
    labels: tuple[str, ...]

    def __post_init__(self) -> None:
        a = np.asarray(self.a_ub, dtype=np.float64)
        b = np.asarray(self.b_ub, dtype=np.float64)
        if a.ndim != 2 or b.shape != (a.shape[0],):
            raise ValueError("invalid linear-system shape")
        if len(self.labels) != a.shape[0]:
            raise ValueError("linear-system label count mismatch")
        if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
            raise ValueError("linear system contains a non-finite value")


@dataclass(frozen=True)
class SolverOutcome:
    """Normalized optimization result."""

    status: str
    feasible: bool
    optimal: bool
    decision: np.ndarray | None
    stream_scale: np.ndarray | None
    objective: float | None
    message: str
    maximum_constraint_excess: float | None
    changed_variable_count: int | None


@dataclass(frozen=True)
class ExactAudit:
    """Exact nonlinear rate and physical-second EESS audit."""

    delivered_total_rate: np.ndarray
    delivered_protected_rate: np.ndarray
    floor_violation_mask: np.ndarray
    floor_violation_count: int
    minimum_active_eligible_floor_ratio: float | None
    maximum_normalized_floor_shortfall: float
    long_ratio: np.ndarray
    short_ratio: np.ndarray
    long_violation_seconds: int
    short_violation_seconds: int
    maximum_long_ratio: float
    maximum_short_ratio: float


@dataclass(frozen=True)
class RepairChoice:
    """One interval's selected candidate action and all solver certificates."""

    status: str
    chosen_action_class: str
    stream_scale: np.ndarray
    sector_scale_equivalent: np.ndarray
    continuous_sector: SolverOutcome
    frozen_grid_sector: SolverOutcome
    local_frozen_grid_sector: SolverOutcome
    sparse_stream: SolverOutcome
    global_stream_oracle: SolverOutcome
    exact_audit: ExactAudit
    mutable_sectors: tuple[int, ...]
    critical_serving_sectors: tuple[int, ...]
    top_external_sectors: tuple[int, ...]
    top_eess_sectors: tuple[int, ...]
    claim_boundary: str


def _as_stream_matrix(value: np.ndarray, *, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 3:
        raise ValueError(f"{name} must have shape [user,sector,stream]")
    return array


def mode_adjusted_amplitude(state: object, q_db: np.ndarray) -> np.ndarray:
    """Return the fixed-beam protected amplitude after mode attenuation."""
    q = np.asarray(q_db, dtype=np.float64)
    perpendicular = np.asarray(state.amp_perpendicular)
    pol1 = np.asarray(state.amp_pol1)
    pol2 = np.asarray(state.amp_pol2)
    if perpendicular.shape != pol1.shape or perpendicular.shape != pol2.shape:
        raise ValueError("protected amplitude components do not align")
    if perpendicular.ndim != 3 or q.shape != (perpendicular.shape[1], 2):
        raise ValueError("invalid q/amplitude shape")
    scale = np.power(10.0, -q / 20.0)
    return (
        perpendicular
        + scale[None, :, 0, None] * pol1
        + scale[None, :, 1, None] * pol2
    )


def mode_adjusted_precoder(matrices: object, q_db: np.ndarray) -> np.ndarray:
    """Return the protected precoder after the fixed mode command."""
    q = np.asarray(q_db, dtype=np.float64)
    p0 = np.asarray(matrices.perpendicular)
    p1 = np.asarray(matrices.polarization_1)
    p2 = np.asarray(matrices.polarization_2)
    if p0.shape != p1.shape or p0.shape != p2.shape:
        raise ValueError("mode matrices do not align")
    if p0.ndim != 3 or q.shape != (p0.shape[0], 2):
        raise ValueError("invalid q/precoder shape")
    scale = np.power(10.0, -q / 20.0)
    return p0 + scale[:, 0, None, None] * p1 + scale[:, 1, None, None] * p2


def stream_leakage_and_power(
    matrices: object,
    q_db: np.ndarray,
    steering_pol1: np.ndarray,
    steering_pol2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-stream EESS leakage and conducted digital power.

    Leakage is the sum of the two protected polarization-mode powers.  The
    returned arrays have shape ``[sector,stream]``.
    """
    precoder = np.asarray(mode_adjusted_precoder(matrices, q_db))
    steering1 = np.asarray(steering_pol1)
    steering2 = np.asarray(steering_pol2)
    if steering1.shape != steering2.shape or steering1.shape != precoder.shape[:2]:
        raise ValueError("steering and precoder dimensions do not align")
    c1 = np.einsum(
        "br,brk->bk", steering1.conj(), precoder, optimize=True
    )
    c2 = np.einsum(
        "br,brk->bk", steering2.conj(), precoder, optimize=True
    )
    leakage = np.abs(c1) ** 2 + np.abs(c2) ** 2
    power = np.sum(np.abs(precoder) ** 2, axis=1)
    return leakage.astype(np.float64), power.astype(np.float64)


def exact_rates_from_stream_scale(
    gain_user_sector_stream: np.ndarray,
    stream_scale: np.ndarray,
    other_weighted_rate: np.ndarray,
    active_user: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate exact fixed-beam rates for arbitrary stream-power scales."""
    gain = _as_stream_matrix(gain_user_sector_stream, name="gain")
    scale = np.asarray(stream_scale, dtype=np.float64)
    active = np.asarray(active_user, dtype=bool)
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    other = np.asarray(other_weighted_rate, dtype=np.float64)
    user_count, sector_count, stream_count = gain.shape
    if scale.shape != (sector_count, stream_count):
        raise ValueError("stream scale has the wrong shape")
    if active.shape != (user_count,) or other.shape != (user_count,):
        raise ValueError("user vector shape mismatch")
    if serving.shape != (user_count,) or stream.shape != (user_count,):
        raise ValueError("serving association shape mismatch")
    if np.any(scale < -1e-14) or np.any(scale > 1.0 + 1e-14):
        raise ValueError("stream scales must lie in [0,1]")
    scale = np.clip(scale, 0.0, 1.0)
    power = gain * scale[None, :, :]
    desired = power[np.arange(user_count), serving, stream]
    total = power.sum(axis=(1, 2))
    interference = np.maximum(total - desired, 0.0)
    protected = np.log2(
        1.0 + desired / (interference + float(protected_noise_w))
    )
    total_rate = other + float(protected_weight) * protected
    total_rate = np.asarray(total_rate, dtype=np.float64)
    protected = np.asarray(protected, dtype=np.float64)
    total_rate[~active] = 0.0
    protected[~active] = 0.0
    return total_rate, protected


def exact_eess_ratio_from_stream_scale(
    kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    stream_scale: np.ndarray,
    allowance_second: np.ndarray,
    coupling_uplift_db: float,
) -> np.ndarray:
    """Evaluate exact normalized aggregate EESS interference every second."""
    kappa = np.asarray(kappa_second_sector, dtype=np.float64)
    leakage = np.asarray(leakage_sector_stream, dtype=np.float64)
    scale = np.asarray(stream_scale, dtype=np.float64)
    allowance = np.asarray(allowance_second, dtype=np.float64)
    if kappa.ndim != 2 or leakage.ndim != 2 or scale.shape != leakage.shape:
        raise ValueError("invalid EESS array shape")
    if kappa.shape[1] != leakage.shape[0] or allowance.shape != (len(kappa),):
        raise ValueError("EESS dimensions do not align")
    if np.any(allowance <= 0.0):
        raise ValueError("EESS allowance must be positive")
    uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
    sector_leakage = np.sum(leakage * scale, axis=1)
    return uplift * (kappa @ sector_leakage) / allowance


def floor_system_for_stream_scales(
    gain_user_sector_stream: np.ndarray,
    other_weighted_rate: np.ndarray,
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
) -> LinearSystem:
    """Build exact linear SINR inequalities for all active eligible floors."""
    gain = _as_stream_matrix(gain_user_sector_stream, name="gain")
    other = np.asarray(other_weighted_rate, dtype=np.float64)
    active = np.asarray(active_user, dtype=bool)
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(floors, dtype=np.float64)
    serving = np.asarray(serving_bs, dtype=np.int64)
    stream = np.asarray(serving_stream, dtype=np.int64)
    user_count, sector_count, stream_count = gain.shape
    for value, name in [
        (other, "other rate"),
        (active, "active"),
        (eligible, "eligible"),
        (floor, "floor"),
        (serving, "serving"),
        (stream, "stream"),
    ]:
        if value.shape != (user_count,):
            raise ValueError(f"{name} vector has the wrong shape")
    if protected_weight <= 0.0 or protected_noise_w <= 0.0:
        raise ValueError("protected weight/noise must be positive")

    rows: list[np.ndarray] = []
    rhs: list[float] = []
    labels: list[str] = []
    flat_gain = gain.reshape(user_count, sector_count * stream_count)
    for user in np.flatnonzero(active & eligible & (floor > 0.0)):
        required_protected_rate = (
            float(floor[user]) - float(other[user])
        ) / float(protected_weight)
        if required_protected_rate <= 0.0:
            continue
        # exp2 is stable here because protected rates are small in this model.
        gamma = math.exp2(required_protected_rate) - 1.0
        desired_index = int(serving[user]) * stream_count + int(stream[user])
        desired_gain = float(flat_gain[user, desired_index])
        row = gamma * flat_gain[user].copy()
        row[desired_index] -= (gamma + 1.0) * desired_gain
        bound = -gamma * float(protected_noise_w)

        # Positive scaling improves numerical conditioning without changing the
        # inequality.  No tolerance is introduced or floor redefined.
        scale = max(float(np.max(np.abs(row))), abs(bound), 1e-30)
        rows.append(row / scale)
        rhs.append(bound / scale)
        labels.append(f"floor:user={int(user)}")

    width = sector_count * stream_count
    if not rows:
        return LinearSystem(
            np.zeros((0, width), dtype=np.float64),
            np.zeros(0, dtype=np.float64),
            tuple(),
        )
    return LinearSystem(np.asarray(rows), np.asarray(rhs), tuple(labels))


def eess_system_for_stream_scales(
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
) -> LinearSystem:
    """Build exact physical-second long/short EESS inequalities."""
    leakage = np.asarray(leakage_sector_stream, dtype=np.float64)
    if leakage.ndim != 2 or np.any(leakage < -1e-15):
        raise ValueError("invalid stream leakage")
    leakage = np.maximum(leakage, 0.0)
    uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
    rows: list[np.ndarray] = []
    rhs: list[float] = []
    labels: list[str] = []
    for criterion, kappa_v, allowance_v in [
        ("long", long_kappa_second_sector, long_allowance_second),
        ("short", short_kappa_second_sector, short_allowance_second),
    ]:
        kappa = np.asarray(kappa_v, dtype=np.float64)
        allowance = np.asarray(allowance_v, dtype=np.float64)
        if kappa.ndim != 2 or kappa.shape[1] != leakage.shape[0]:
            raise ValueError(f"invalid {criterion} kappa shape")
        if allowance.shape != (len(kappa),) or np.any(allowance <= 0.0):
            raise ValueError(f"invalid {criterion} allowance")
        coefficient = (
            uplift
            * kappa[:, :, None]
            * leakage[None, :, :]
            / allowance[:, None, None]
        ).reshape(len(kappa), -1)
        rows.extend(coefficient)
        rhs.extend(np.ones(len(kappa), dtype=np.float64))
        labels.extend(
            f"eess:{criterion}:second={second}" for second in range(len(kappa))
        )
    return LinearSystem(np.asarray(rows), np.asarray(rhs), tuple(labels))


def combine_systems(*systems: LinearSystem) -> LinearSystem:
    """Vertically concatenate compatible labelled systems."""
    widths = {system.a_ub.shape[1] for system in systems}
    if len(widths) != 1:
        raise ValueError("linear-system widths do not match")
    width = next(iter(widths))
    nonempty = [system for system in systems if len(system.b_ub)]
    if not nonempty:
        return LinearSystem(
            np.zeros((0, width), dtype=np.float64),
            np.zeros(0, dtype=np.float64),
            tuple(),
        )
    return LinearSystem(
        np.vstack([system.a_ub for system in nonempty]),
        np.concatenate([system.b_ub for system in nonempty]),
        tuple(label for system in nonempty for label in system.labels),
    )


def sector_mapping(sector_count: int, stream_count: int) -> np.ndarray:
    """Map one sector scale to all streams in that sector."""
    mapping = np.zeros(
        (sector_count * stream_count, sector_count), dtype=np.float64
    )
    for sector in range(sector_count):
        start = sector * stream_count
        mapping[start : start + stream_count, sector] = 1.0
    return mapping


def mapped_system(
    stream_system: LinearSystem,
    mapping: np.ndarray,
    offset: np.ndarray,
) -> LinearSystem:
    """Substitute ``stream_scale = offset + mapping @ decision``."""
    matrix = np.asarray(mapping, dtype=np.float64)
    fixed = np.asarray(offset, dtype=np.float64)
    if matrix.ndim != 2 or fixed.shape != (matrix.shape[0],):
        raise ValueError("invalid mapping/offset shape")
    if stream_system.a_ub.shape[1] != matrix.shape[0]:
        raise ValueError("mapping does not match stream system")
    return LinearSystem(
        stream_system.a_ub @ matrix,
        stream_system.b_ub - stream_system.a_ub @ fixed,
        stream_system.labels,
    )


def _maximum_excess(system: LinearSystem, decision: np.ndarray) -> float:
    if not len(system.b_ub):
        return -math.inf
    return float(np.max(system.a_ub @ decision - system.b_ub))


def solve_continuous_l1(
    stream_system: LinearSystem,
    mapping: np.ndarray,
    offset: np.ndarray,
    baseline_decision: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    l1_weight: np.ndarray | None = None,
    extra_system: LinearSystem | None = None,
) -> SolverOutcome:
    """Find a hard-feasible action with minimum weighted L1 change."""
    matrix = np.asarray(mapping, dtype=np.float64)
    fixed = np.asarray(offset, dtype=np.float64)
    baseline = np.asarray(baseline_decision, dtype=np.float64)
    lower_v = np.asarray(lower, dtype=np.float64)
    upper_v = np.asarray(upper, dtype=np.float64)
    variable_count = matrix.shape[1]
    if baseline.shape != (variable_count,):
        raise ValueError("baseline decision has the wrong shape")
    if lower_v.shape != baseline.shape or upper_v.shape != baseline.shape:
        raise ValueError("decision bounds have the wrong shape")
    if np.any(lower_v > upper_v):
        raise ValueError("invalid decision bounds")
    if l1_weight is None:
        weight = np.ones(variable_count, dtype=np.float64)
    else:
        weight = np.asarray(l1_weight, dtype=np.float64)
        if weight.shape != baseline.shape or np.any(weight <= 0.0):
            raise ValueError("invalid L1 weights")

    system = mapped_system(stream_system, matrix, fixed)
    if extra_system is not None:
        if extra_system.a_ub.shape[1] != variable_count:
            raise ValueError("extra decision-system width mismatch")
        system = combine_systems(system, extra_system)

    # Exact no-op shortcut.
    baseline_excess = _maximum_excess(system, baseline)
    if baseline_excess <= 0.0:
        stream = fixed + matrix @ baseline
        return SolverOutcome(
            status="FEASIBLE_BASELINE_NOOP",
            feasible=True,
            optimal=True,
            decision=baseline.copy(),
            stream_scale=stream.reshape(-1),
            objective=0.0,
            message="reviewed baseline already satisfies all hard constraints",
            maximum_constraint_excess=baseline_excess,
            changed_variable_count=0,
        )

    # Variables are [decision, absolute-deviation].
    n = variable_count
    c = np.concatenate([np.zeros(n), weight])
    hard = csr_matrix(system.a_ub)
    zero = csr_matrix((hard.shape[0], n), dtype=np.float64)
    a_hard = hstack([hard, zero], format="csr")

    ident = sparse_eye(n, format="csr")
    # decision - deviation <= baseline
    # -decision - deviation <= -baseline
    a_dev = vstack(
        [hstack([ident, -ident]), hstack([-ident, -ident])],
        format="csr",
    )
    b_dev = np.concatenate([baseline, -baseline])
    a_ub = vstack([a_hard, a_dev], format="csr")
    b_ub = np.concatenate([system.b_ub, b_dev])
    bounds = list(zip(lower_v, upper_v)) + [(0.0, None)] * n
    result = linprog(
        c,
        A_ub=a_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",
        options={"presolve": True},
    )
    if not result.success:
        status = "INFEASIBLE" if result.status == 2 else "SOLVER_FAILED"
        return SolverOutcome(
            status=status,
            feasible=False,
            optimal=False,
            decision=None,
            stream_scale=None,
            objective=None,
            message=str(result.message),
            maximum_constraint_excess=None,
            changed_variable_count=None,
        )
    decision = np.asarray(result.x[:n], dtype=np.float64)
    stream = fixed + matrix @ decision
    excess = _maximum_excess(system, decision)
    feasible = excess <= 5e-9
    return SolverOutcome(
        status="OPTIMAL_CONTINUOUS_L1" if feasible else "NUMERICAL_VERIFICATION_FAIL",
        feasible=feasible,
        optimal=bool(feasible),
        decision=decision,
        stream_scale=stream,
        objective=float(result.fun),
        message=str(result.message),
        maximum_constraint_excess=excess,
        changed_variable_count=int(np.sum(np.abs(decision - baseline) > 1e-8)),
    )


def solve_frozen_sector_grid(
    sector_system: LinearSystem,
    baseline_sector_scale: np.ndarray,
    grid_backoff_db: Sequence[float],
    *,
    maximum_scale: np.ndarray | None = None,
    time_limit_s: float = 60.0,
) -> SolverOutcome:
    """Solve the exact frozen 0--12 dB plus mute sector action class."""
    baseline = np.asarray(baseline_sector_scale, dtype=np.float64)
    sector_count = len(baseline)
    if sector_system.a_ub.shape[1] != sector_count:
        raise ValueError("sector system width mismatch")
    backoff = np.asarray(tuple(grid_backoff_db), dtype=np.float64)
    if backoff.ndim != 1 or not np.any(np.isinf(backoff)):
        raise ValueError("grid must include the exact mute endpoint")
    scale = np.zeros_like(backoff)
    finite = np.isfinite(backoff)
    scale[finite] = np.power(10.0, -backoff[finite] / 10.0)
    choices = len(scale)
    if maximum_scale is None:
        maximum = np.ones(sector_count, dtype=np.float64)
    else:
        maximum = np.asarray(maximum_scale, dtype=np.float64)
        if maximum.shape != (sector_count,) or np.any(maximum < 0.0):
            raise ValueError("maximum_scale has the wrong shape")

    # One binary choice per sector/locally mutable scalar variable.
    z_to_x = np.zeros((sector_count, sector_count * choices), dtype=np.float64)
    equality = np.zeros_like(z_to_x)
    objective = np.empty(sector_count * choices, dtype=np.float64)
    for sector in range(sector_count):
        sl = slice(sector * choices, (sector + 1) * choices)
        z_to_x[sector, sl] = scale
        equality[sector, sl] = 1.0
        objective[sl] = np.abs(scale - baseline[sector])

    hard = sector_system.a_ub @ z_to_x
    constraint = LinearConstraint(
        csr_matrix(np.vstack([equality, hard])),
        np.concatenate([np.ones(sector_count), np.full(len(hard), -np.inf)]),
        np.concatenate([np.ones(sector_count), sector_system.b_ub]),
    )
    upper_z = np.ones(sector_count * choices, dtype=np.float64)
    for sector in range(sector_count):
        sl = slice(sector * choices, (sector + 1) * choices)
        upper_z[sl] = (scale <= maximum[sector] + 1e-12).astype(np.float64)
        if not np.any(upper_z[sl] > 0.5):
            raise ValueError(f"no grid choice satisfies maximum_scale for variable {sector}")
    result = milp(
        c=objective,
        integrality=np.ones(sector_count * choices, dtype=np.int8),
        bounds=Bounds(np.zeros_like(upper_z), upper_z),
        constraints=constraint,
        options={
            "presolve": True,
            "time_limit": float(time_limit_s),
            "mip_rel_gap": 0.0,
        },
    )
    if result.x is None:
        if result.status == 2:
            status = "PROVEN_INFEASIBLE_FROZEN_GRID"
        elif result.status == 1:
            status = "UNRESOLVED_TIME_LIMIT_FROZEN_GRID"
        else:
            status = "SOLVER_FAILED_FROZEN_GRID"
        return SolverOutcome(
            status=status,
            feasible=False,
            optimal=False,
            decision=None,
            stream_scale=None,
            objective=None,
            message=str(result.message),
            maximum_constraint_excess=None,
            changed_variable_count=None,
        )
    z = np.asarray(result.x).reshape(sector_count, choices)
    selected = np.argmax(z, axis=1)
    decision = scale[selected]
    excess = _maximum_excess(sector_system, decision)
    feasible = excess <= 5e-9
    return SolverOutcome(
        status=(
            "OPTIMAL_FROZEN_GRID"
            if result.status == 0 and feasible
            else "FEASIBLE_NOT_PROVEN_OPTIMAL_FROZEN_GRID"
            if feasible
            else "NUMERICAL_VERIFICATION_FAIL_FROZEN_GRID"
        ),
        feasible=feasible,
        optimal=bool(result.status == 0 and feasible),
        decision=decision,
        stream_scale=None,
        objective=float(result.fun) if result.fun is not None else None,
        message=str(result.message),
        maximum_constraint_excess=excess,
        changed_variable_count=int(np.sum(np.abs(decision - baseline) > 1e-8)),
    )


def top_external_interfering_sectors(
    gain_user_sector_stream: np.ndarray,
    baseline_stream_scale: np.ndarray,
    violating_users: Iterable[int],
    serving_bs: np.ndarray,
    *,
    per_user: int,
) -> tuple[int, ...]:
    """Return a deterministic sparse neighbourhood of external interferers."""
    gain = _as_stream_matrix(gain_user_sector_stream, name="gain")
    scale = np.asarray(baseline_stream_scale, dtype=np.float64)
    serving = np.asarray(serving_bs, dtype=np.int64)
    sectors: set[int] = set()
    for user in sorted(set(int(value) for value in violating_users)):
        contribution = np.sum(gain[user] * scale, axis=1)
        contribution[int(serving[user])] = -math.inf
        order = np.argsort(-contribution, kind="stable")
        selected = [
            int(value)
            for value in order
            if np.isfinite(contribution[value]) and contribution[value] > 0.0
        ][: int(per_user)]
        sectors.update(selected)
    return tuple(sorted(sectors))



def top_eess_contributing_sectors(
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    baseline_stream_scale: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
    *,
    count: int,
    stress_sectors: Sequence[int] = (),
    excluded_sectors: Sequence[int] = (),
) -> tuple[int, ...]:
    """Return a bounded set of sectors that can release EESS headroom.

    Current violation rows are always included in the ranking.  When a floor
    repair may restore one or more serving sectors toward nominal power, the
    most binding long- and short-term rows under that conservative stress are
    included even if the reviewed baseline is presently EESS-safe.  This avoids
    a false local infeasibility caused by omitting a non-interfering sector whose
    backoff can fund the serving-sector restoration.  The exact LP/MILP still
    enforces every physical-second row; this function only selects at most
    ``count`` deployable scalar neighbours.
    """
    leakage = np.asarray(leakage_sector_stream, dtype=np.float64)
    scale = np.asarray(baseline_stream_scale, dtype=np.float64)
    if leakage.ndim != 2 or scale.shape != leakage.shape:
        raise ValueError("invalid EESS ranking arrays")
    if count < 0:
        raise ValueError("EESS neighbourhood size must be nonnegative")
    sector_count = leakage.shape[0]
    stress = tuple(sorted(set(int(v) for v in stress_sectors)))
    excluded = tuple(sorted(set(int(v) for v in excluded_sectors)))
    if any(v < 0 or v >= sector_count for v in stress + excluded):
        raise ValueError("EESS ranking sector out of range")

    sector_leakage = np.sum(leakage * scale, axis=1)
    stressed_sector_leakage = sector_leakage.copy()
    for sector in stress:
        stressed_sector_leakage[sector] = float(np.sum(leakage[sector]))

    uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
    score = np.zeros(sector_count, dtype=np.float64)
    for kappa_v, allowance_v in [
        (long_kappa_second_sector, long_allowance_second),
        (short_kappa_second_sector, short_allowance_second),
    ]:
        kappa = np.asarray(kappa_v, dtype=np.float64)
        allowance = np.asarray(allowance_v, dtype=np.float64)
        if kappa.ndim != 2 or kappa.shape[1] != sector_count:
            raise ValueError("invalid EESS ranking kappa")
        if allowance.shape != (len(kappa),) or np.any(allowance <= 0.0):
            raise ValueError("invalid EESS ranking allowance")
        if len(kappa) == 0:
            continue
        contribution = (
            uplift * kappa * sector_leakage[None, :] / allowance[:, None]
        )
        baseline_ratio = np.sum(contribution, axis=1)
        selected_rows = baseline_ratio > (1.0 + EESS_VERIFICATION_TOLERANCE)
        if stress:
            stressed_ratio = (
                uplift * (kappa @ stressed_sector_leakage) / allowance
            )
            selected_rows[int(np.argmax(stressed_ratio))] = True
        elif not np.any(selected_rows) and np.any(baseline_ratio > 0.0):
            selected_rows[int(np.argmax(baseline_ratio))] = True
        if np.any(selected_rows):
            score = np.maximum(
                score, np.max(contribution[selected_rows], axis=0)
            )

    if excluded:
        score[np.asarray(excluded, dtype=np.int64)] = 0.0
    if count == 0 or not np.any(score > 0.0):
        return tuple()
    order = np.argsort(-score, kind="stable")
    selected = [int(v) for v in order if score[v] > 0.0][: int(count)]
    return tuple(sorted(selected))


def sparse_sector_mapping(
    baseline_sector_scale: np.ndarray,
    mutable_sectors: Sequence[int],
    *,
    stream_count: int = 4,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, ...]]:
    """Map a sparse set of sector scalars while freezing every other sector.

    The selected variables remain exact members of the frozen sector-scale action
    class when their values are restricted to the configured dB/mute grid.
    """
    baseline = np.asarray(baseline_sector_scale, dtype=np.float64)
    mutable = tuple(sorted(set(int(v) for v in mutable_sectors)))
    sector_count = len(baseline)
    if any(v < 0 or v >= sector_count for v in mutable):
        raise ValueError("mutable sector out of range")
    offset = np.repeat(baseline, stream_count)
    mapping = np.zeros(
        (sector_count * stream_count, len(mutable)), dtype=np.float64
    )
    for column, sector in enumerate(mutable):
        sl = slice(sector * stream_count, (sector + 1) * stream_count)
        offset[sl] = 0.0
        mapping[sl, column] = 1.0
    return mapping, offset, baseline[np.asarray(mutable, dtype=np.int64)], mutable

def sparse_hybrid_mapping(
    baseline_sector_scale: np.ndarray,
    critical_serving_sectors: Sequence[int],
    external_scalar_sectors: Sequence[int],
    *,
    stream_count: int = 4,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    """Map local stream variables and sparse external scalar variables.

    Critical serving sectors receive four continuous stream weights.  Selected
    external sectors receive one continuous scalar applied to all four streams.
    All other sectors remain exactly at the reviewed fallback action.
    """
    baseline = np.asarray(baseline_sector_scale, dtype=np.float64)
    critical = tuple(sorted(set(int(v) for v in critical_serving_sectors)))
    external = tuple(
        sorted(set(int(v) for v in external_scalar_sectors) - set(critical))
    )
    sector_count = len(baseline)
    offset = np.repeat(baseline, stream_count)
    columns: list[np.ndarray] = []
    baseline_decision: list[float] = []
    names: list[str] = []

    for sector in critical:
        sl = slice(sector * stream_count, (sector + 1) * stream_count)
        offset[sl] = 0.0
        for local_stream in range(stream_count):
            column = np.zeros(sector_count * stream_count, dtype=np.float64)
            column[sector * stream_count + local_stream] = 1.0
            columns.append(column)
            baseline_decision.append(float(baseline[sector]))
            names.append(f"sector={sector}:stream={local_stream}")
    for sector in external:
        sl = slice(sector * stream_count, (sector + 1) * stream_count)
        offset[sl] = 0.0
        column = np.zeros(sector_count * stream_count, dtype=np.float64)
        column[sl] = 1.0
        columns.append(column)
        baseline_decision.append(float(baseline[sector]))
        names.append(f"sector={sector}:scalar")

    if columns:
        mapping = np.column_stack(columns)
    else:
        mapping = np.zeros((sector_count * stream_count, 0), dtype=np.float64)
    return (
        mapping,
        offset,
        np.asarray(baseline_decision, dtype=np.float64),
        tuple(names),
    )


def local_sector_power_budget_system(
    *,
    mapping: np.ndarray,
    offset: np.ndarray,
    stream_power: np.ndarray,
    baseline_sector_scale: np.ndarray,
    constrained_sectors: Sequence[int],
) -> LinearSystem:
    """Return decision-space per-sector protected-power budget rows.

    For every constrained sector, the candidate's conducted protected-subband
    power may not exceed the reviewed fallback's sector power.  This permits
    redistribution among fixed RZF streams without silently adding power.
    """
    matrix = np.asarray(mapping, dtype=np.float64)
    fixed = np.asarray(offset, dtype=np.float64)
    power = np.asarray(stream_power, dtype=np.float64)
    baseline = np.asarray(baseline_sector_scale, dtype=np.float64)
    if power.ndim != 2 or baseline.shape != (power.shape[0],):
        raise ValueError("invalid sector-power budget inputs")
    if matrix.shape[0] != power.size or fixed.shape != (power.size,):
        raise ValueError("mapping does not align with stream power")
    rows: list[np.ndarray] = []
    rhs: list[float] = []
    labels: list[str] = []
    flat_power = power.reshape(-1)
    for sector in sorted(set(int(v) for v in constrained_sectors)):
        if sector < 0 or sector >= power.shape[0]:
            raise ValueError("constrained sector out of range")
        selector = np.zeros_like(flat_power)
        start = sector * power.shape[1]
        stop = start + power.shape[1]
        selector[start:stop] = flat_power[start:stop]
        row = selector @ matrix
        bound = (
            baseline[sector] * float(np.sum(power[sector]))
            - float(selector @ fixed)
        )
        scale = max(float(np.max(np.abs(row))) if row.size else 0.0, abs(bound), 1e-30)
        rows.append(np.asarray(row, dtype=np.float64) / scale)
        rhs.append(float(bound) / scale)
        labels.append(f"power_budget:sector={sector}")
    if not rows:
        return LinearSystem(
            np.zeros((0, matrix.shape[1]), dtype=np.float64),
            np.zeros(0, dtype=np.float64),
            tuple(),
        )
    return LinearSystem(np.vstack(rows), np.asarray(rhs), tuple(labels))


def exact_audit(
    *,
    gain_user_sector_stream: np.ndarray,
    stream_scale: np.ndarray,
    other_weighted_rate: np.ndarray,
    active_user: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
) -> ExactAudit:
    """Perform exact nonlinear verification without weakening any gate."""
    total, protected = exact_rates_from_stream_scale(
        gain_user_sector_stream,
        stream_scale,
        other_weighted_rate,
        active_user,
        serving_bs,
        serving_stream,
        protected_noise_w,
        protected_weight,
    )
    active = np.asarray(active_user, dtype=bool)
    eligible = np.asarray(eligible_user, dtype=bool)
    floor = np.asarray(floors, dtype=np.float64)
    valid = active & eligible & (floor > 0.0)
    violation = valid & (total < floor - FLOOR_COMPARISON_TOLERANCE)
    if np.any(valid):
        ratio = total[valid] / floor[valid]
        minimum_ratio: float | None = float(np.min(ratio))
        normalized = np.maximum(0.0, (floor[valid] - total[valid]) / floor[valid])
        maximum_shortfall = float(np.max(normalized))
    else:
        minimum_ratio = None
        maximum_shortfall = 0.0
    long_ratio = exact_eess_ratio_from_stream_scale(
        long_kappa_second_sector,
        leakage_sector_stream,
        stream_scale,
        long_allowance_second,
        coupling_uplift_db,
    )
    short_ratio = exact_eess_ratio_from_stream_scale(
        short_kappa_second_sector,
        leakage_sector_stream,
        stream_scale,
        short_allowance_second,
        coupling_uplift_db,
    )
    return ExactAudit(
        delivered_total_rate=total,
        delivered_protected_rate=protected,
        floor_violation_mask=violation,
        floor_violation_count=int(np.sum(violation)),
        minimum_active_eligible_floor_ratio=minimum_ratio,
        maximum_normalized_floor_shortfall=maximum_shortfall,
        long_ratio=long_ratio,
        short_ratio=short_ratio,
        long_violation_seconds=int(
            np.sum(long_ratio > 1.0 + EESS_VERIFICATION_TOLERANCE)
        ),
        short_violation_seconds=int(
            np.sum(short_ratio > 1.0 + EESS_VERIFICATION_TOLERANCE)
        ),
        maximum_long_ratio=float(np.max(long_ratio)),
        maximum_short_ratio=float(np.max(short_ratio)),
    )


def optimistic_single_user_upper_bound(
    *,
    user: int,
    gain_user_sector_stream: np.ndarray,
    other_weighted_rate: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    leakage_sector_stream: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
) -> dict[str, float | int]:
    """Return an optimistic fixed-q/fixed-beam single-user rate upper bound.

    Every other protected stream is muted.  The target stream may use up to its
    nominal scale, additionally limited by every long/short physical-second EESS
    row.  Failure of this optimistic bound is a valid infeasibility certificate
    only for the fixed-q, fixed-beam protected-subband class.
    """
    gain = _as_stream_matrix(gain_user_sector_stream, name="gain")
    leakage = np.asarray(leakage_sector_stream, dtype=np.float64)
    bs = int(np.asarray(serving_bs)[user])
    stream = int(np.asarray(serving_stream)[user])
    uplift = 10.0 ** (float(coupling_uplift_db) / 10.0)
    coefficient_rows: list[np.ndarray] = []
    for kappa_v, allowance_v in [
        (long_kappa_second_sector, long_allowance_second),
        (short_kappa_second_sector, short_allowance_second),
    ]:
        kappa = np.asarray(kappa_v, dtype=np.float64)
        allowance = np.asarray(allowance_v, dtype=np.float64)
        coefficient_rows.append(
            uplift * kappa[:, bs] * leakage[bs, stream] / allowance
        )
    coefficient = np.concatenate(coefficient_rows)
    positive = coefficient > 0.0
    eess_limited_scale = (
        float(np.min(1.0 / coefficient[positive])) if np.any(positive) else 1.0
    )
    scale = min(1.0, eess_limited_scale)
    desired = float(gain[user, bs, stream]) * scale
    protected = math.log2(1.0 + desired / float(protected_noise_w))
    total = float(other_weighted_rate[user]) + float(protected_weight) * protected
    return {
        "user_index": int(user),
        "serving_sector": bs,
        "serving_stream": stream,
        "maximum_target_stream_scale": float(scale),
        "eess_limited_target_stream_scale": float(eess_limited_scale),
        "optimistic_protected_rate_bps_hz": float(protected),
        "optimistic_total_rate_bps_hz": float(total),
    }


def repair_interval(
    *,
    state: object,
    matrices: object,
    q_db: np.ndarray,
    baseline_sector_scale: np.ndarray,
    eligible_user: np.ndarray,
    floors: np.ndarray,
    serving_bs: np.ndarray,
    serving_stream: np.ndarray,
    protected_noise_w: float,
    protected_weight: float,
    steering_pol1: np.ndarray,
    steering_pol2: np.ndarray,
    long_kappa_second_sector: np.ndarray,
    short_kappa_second_sector: np.ndarray,
    long_allowance_second: np.ndarray,
    short_allowance_second: np.ndarray,
    coupling_uplift_db: float,
    grid_backoff_db: Sequence[float],
    external_neighbourhood_sizes: Sequence[int] = (2,),
    eess_neighbourhood_size: int = 2,
    grid_time_limit_s: float = 60.0,
) -> RepairChoice:
    """Run the lexicographic repair hierarchy for one interval.

    Hierarchy:
      1. continuous sector-scale feasibility relaxation;
      2. sparse local frozen-grid repair, which is also a global-grid witness;
      3. global frozen-grid oracle only if no sparse witness is found;
      4. sparse local stream-power repair with a bounded neighbourhood;
      5. global stream-power feasibility oracle;
      6. class-specific infeasibility/unresolved certificate.
    """
    q = np.asarray(q_db, dtype=np.float64)
    baseline_sector = np.asarray(baseline_sector_scale, dtype=np.float64)
    neighbourhood_sizes = tuple(int(v) for v in external_neighbourhood_sizes)
    if not neighbourhood_sizes or any(v < 0 or v > 2 for v in neighbourhood_sizes):
        raise ValueError(
            "deployable external neighbourhood sizes must lie in [0,2]; "
            "larger/global actions are diagnostic oracles only"
        )
    if int(eess_neighbourhood_size) < 0 or int(eess_neighbourhood_size) > 2:
        raise ValueError(
            "deployable EESS neighbourhood must contain at most two sectors"
        )
    configured_backoff = np.asarray(tuple(grid_backoff_db), dtype=np.float64)
    configured_scale = np.zeros_like(configured_backoff)
    configured_finite = np.isfinite(configured_backoff)
    configured_scale[configured_finite] = np.power(
        10.0, -configured_backoff[configured_finite] / 10.0
    )
    if baseline_sector.ndim != 1 or np.any(
        np.min(
            np.abs(baseline_sector[:, None] - configured_scale[None, :]),
            axis=1,
        )
        > 1e-10
    ):
        raise ValueError(
            "baseline sector action must be an exact member of the frozen grid"
        )
    amplitude = mode_adjusted_amplitude(state, q)
    gain = np.abs(amplitude) ** 2
    leakage, stream_power = stream_leakage_and_power(
        matrices, q, steering_pol1, steering_pol2
    )
    floor_system = floor_system_for_stream_scales(
        gain,
        np.asarray(state.other_weighted_rate, dtype=np.float64),
        np.asarray(state.active_user, dtype=bool),
        eligible_user,
        floors,
        serving_bs,
        serving_stream,
        protected_noise_w,
        protected_weight,
    )
    eess_system = eess_system_for_stream_scales(
        long_kappa_second_sector,
        short_kappa_second_sector,
        leakage,
        long_allowance_second,
        short_allowance_second,
        coupling_uplift_db,
    )
    hard_stream = combine_systems(floor_system, eess_system)
    sector_map = sector_mapping(gain.shape[1], gain.shape[2])
    baseline_stream = np.repeat(baseline_sector, gain.shape[2])

    continuous_sector = solve_continuous_l1(
        hard_stream,
        sector_map,
        np.zeros(gain.shape[1] * gain.shape[2]),
        baseline_sector,
        np.zeros_like(baseline_sector),
        np.ones_like(baseline_sector),
    )
    sector_system = mapped_system(
        hard_stream,
        sector_map,
        np.zeros(gain.shape[1] * gain.shape[2]),
    )

    baseline_audit = exact_audit(
        gain_user_sector_stream=gain,
        stream_scale=baseline_stream.reshape(gain.shape[1], gain.shape[2]),
        other_weighted_rate=state.other_weighted_rate,
        active_user=state.active_user,
        eligible_user=eligible_user,
        floors=floors,
        serving_bs=serving_bs,
        serving_stream=serving_stream,
        protected_noise_w=protected_noise_w,
        protected_weight=protected_weight,
        long_kappa_second_sector=long_kappa_second_sector,
        short_kappa_second_sector=short_kappa_second_sector,
        leakage_sector_stream=leakage,
        long_allowance_second=long_allowance_second,
        short_allowance_second=short_allowance_second,
        coupling_uplift_db=coupling_uplift_db,
    )
    violating_users = np.flatnonzero(baseline_audit.floor_violation_mask)
    critical = tuple(
        sorted(set(int(np.asarray(serving_bs)[u]) for u in violating_users))
    )
    eess_candidates = top_eess_contributing_sectors(
        long_kappa_second_sector,
        short_kappa_second_sector,
        leakage,
        baseline_stream.reshape(gain.shape[1], gain.shape[2]),
        long_allowance_second,
        short_allowance_second,
        coupling_uplift_db,
        count=int(eess_neighbourhood_size),
        stress_sectors=critical,
        excluded_sectors=critical,
    )

    baseline_hard_pass = (
        baseline_audit.floor_violation_count == 0
        and baseline_audit.long_violation_seconds == 0
        and baseline_audit.short_violation_seconds == 0
    )

    local_grid = SolverOutcome(
        status=(
            "NOT_NEEDED_BASELINE_FEASIBLE"
            if baseline_hard_pass
            else "NOT_ATTEMPTED"
        ),
        feasible=bool(baseline_hard_pass),
        optimal=bool(baseline_hard_pass),
        decision=(baseline_sector[np.asarray(critical, dtype=np.int64)].copy() if baseline_hard_pass else None),
        stream_scale=(baseline_stream.copy() if baseline_hard_pass else None),
        objective=0.0 if baseline_hard_pass else None,
        message=(
            "reviewed baseline already satisfies all hard constraints"
            if baseline_hard_pass
            else "no sparse local frozen-grid repair attempted"
        ),
        maximum_constraint_excess=0.0 if baseline_hard_pass else None,
        changed_variable_count=0 if baseline_hard_pass else None,
    )
    selected_external: tuple[int, ...] = tuple()
    selected_eess: tuple[int, ...] = tuple()
    if not baseline_hard_pass:
        if continuous_sector.status == "INFEASIBLE":
            local_grid = SolverOutcome(
                status="PROVEN_INFEASIBLE_LOCAL_GRID_BY_GLOBAL_CONTINUOUS_RELAXATION",
                feasible=False,
                optimal=False,
                decision=None,
                stream_scale=None,
                objective=None,
                message=(
                    "the global continuous sector-scale class is infeasible; "
                    "every sparse local frozen-grid subset is infeasible"
                ),
                maximum_constraint_excess=None,
                changed_variable_count=None,
            )
        else:
            for count in neighbourhood_sizes:
                external = top_external_interfering_sectors(
                    gain,
                    baseline_stream.reshape(gain.shape[1], gain.shape[2]),
                    violating_users,
                    serving_bs,
                    per_user=min(int(count), gain.shape[1] - 1),
                )
                mutable_requested = tuple(
                    sorted(set(critical) | set(external) | set(eess_candidates))
                )
                mapping, offset, base_decision, mutable = sparse_sector_mapping(
                    baseline_sector,
                    mutable_requested,
                    stream_count=gain.shape[2],
                )
                if mapping.shape[1] == 0:
                    continue
                local_system = mapped_system(hard_stream, mapping, offset)
                maximum = np.asarray(
                    [
                        1.0 if sector in critical else baseline_sector[sector]
                        for sector in mutable
                    ],
                    dtype=np.float64,
                )
                trial = solve_frozen_sector_grid(
                    local_system,
                    base_decision,
                    grid_backoff_db,
                    maximum_scale=maximum,
                    time_limit_s=min(float(grid_time_limit_s), 10.0),
                )
                if trial.feasible and trial.decision is not None:
                    full_stream = offset + mapping @ trial.decision
                    local_grid = SolverOutcome(
                        status="FEASIBLE_SPARSE_LOCAL_FROZEN_GRID",
                        feasible=True,
                        optimal=trial.optimal,
                        decision=np.asarray(trial.decision),
                        stream_scale=np.asarray(full_stream),
                        objective=trial.objective,
                        message=trial.message,
                        maximum_constraint_excess=trial.maximum_constraint_excess,
                        changed_variable_count=trial.changed_variable_count,
                    )
                    selected_external = tuple(
                        sorted(set(external) - set(critical))
                    )
                    selected_eess = tuple(
                        sorted(set(eess_candidates) - set(critical))
                    )
                    break
                local_grid = SolverOutcome(
                    status=trial.status,
                    feasible=False,
                    optimal=False,
                    decision=None,
                    stream_scale=None,
                    objective=None,
                    message=trial.message,
                    maximum_constraint_excess=trial.maximum_constraint_excess,
                    changed_variable_count=trial.changed_variable_count,
                )

    # Determine the global frozen action-space feasibility only after the
    # sparse local grid.  A feasible sparse action is already an exact witness
    # for the global grid and avoids solving an unnecessary 57-sector MILP.
    if local_grid.feasible and local_grid.stream_scale is not None:
        local_stream_matrix = np.asarray(local_grid.stream_scale).reshape(
            gain.shape[1], gain.shape[2]
        )
        if not np.allclose(
            local_stream_matrix,
            local_stream_matrix[:, :1],
            rtol=0.0,
            atol=1e-12,
        ):
            raise RuntimeError("local frozen-grid witness is not sector-scalar")
        full_sector_witness = local_stream_matrix[:, 0].copy()
        frozen_grid = SolverOutcome(
            status="FEASIBLE_BY_SPARSE_LOCAL_GRID_SUBSET",
            feasible=True,
            optimal=False,
            decision=full_sector_witness,
            stream_scale=np.repeat(full_sector_witness, gain.shape[2]),
            objective=local_grid.objective,
            message=(
                "the sparse local frozen-grid action is an exact witness in "
                "the global frozen sector action class"
            ),
            maximum_constraint_excess=local_grid.maximum_constraint_excess,
            changed_variable_count=int(
                np.sum(np.abs(full_sector_witness - baseline_sector) > 1e-8)
            ),
        )
    elif continuous_sector.status == "INFEASIBLE":
        frozen_grid = SolverOutcome(
            status="PROVEN_INFEASIBLE_FROZEN_GRID_BY_CONTINUOUS_RELAXATION",
            feasible=False,
            optimal=False,
            decision=None,
            stream_scale=None,
            objective=None,
            message=(
                "the exact continuous sector-scale relaxation is infeasible; "
                "the frozen grid is a subset"
            ),
            maximum_constraint_excess=None,
            changed_variable_count=None,
        )
    elif continuous_sector.feasible:
        frozen_grid = solve_frozen_sector_grid(
            sector_system,
            baseline_sector,
            grid_backoff_db,
            time_limit_s=grid_time_limit_s,
        )
    else:
        frozen_grid = SolverOutcome(
            status="UNRESOLVED_FROZEN_GRID_CONTINUOUS_SOLVER_FAILURE",
            feasible=False,
            optimal=False,
            decision=None,
            stream_scale=None,
            objective=None,
            message=continuous_sector.message,
            maximum_constraint_excess=None,
            changed_variable_count=None,
        )

    sparse_outcome = SolverOutcome(
        status=(
            "NOT_NEEDED_LOCAL_GRID_FEASIBLE"
            if local_grid.feasible
            else "NOT_ATTEMPTED"
        ),
        feasible=bool(local_grid.feasible),
        optimal=False,
        decision=None,
        stream_scale=(
            np.asarray(local_grid.stream_scale)
            if local_grid.feasible and local_grid.stream_scale is not None
            else None
        ),
        objective=None,
        message=(
            "a sparse local frozen-grid action is already feasible"
            if local_grid.feasible
            else "no sparse stream repair attempted"
        ),
        maximum_constraint_excess=local_grid.maximum_constraint_excess,
        changed_variable_count=local_grid.changed_variable_count,
    )
    if not baseline_hard_pass and not local_grid.feasible:
        for count in neighbourhood_sizes:
            external = top_external_interfering_sectors(
                gain,
                baseline_stream.reshape(gain.shape[1], gain.shape[2]),
                violating_users,
                serving_bs,
                per_user=min(int(count), gain.shape[1] - 1),
            )
            external_all = tuple(sorted(set(external) | set(eess_candidates)))
            mapping, offset, base_decision, _names = sparse_hybrid_mapping(
                baseline_sector,
                critical,
                external_all,
                stream_count=gain.shape[2],
            )
            if mapping.shape[1] == 0:
                continue
            # Physical-power weights prevent arbitrary stream reshuffling after
            # hard feasibility has been achieved.
            weights: list[float] = []
            for sector in critical:
                weights.extend(
                    np.maximum(stream_power[sector], 1e-12).tolist()
                )
            external_only = tuple(
                sorted(set(external_all) - set(critical))
            )
            for sector in external_only:
                weights.append(float(max(np.sum(stream_power[sector]), 1e-12)))
            lower = np.zeros_like(base_decision)
            upper = np.ones_like(base_decision)
            # External scalar variables are interferer-backoff variables only.
            # They may not increase above the reviewed fallback scale.
            critical_variable_count = len(critical) * gain.shape[2]
            for index, sector in enumerate(
                external_only, start=critical_variable_count
            ):
                upper[index] = baseline_sector[sector]
            budget_system = local_sector_power_budget_system(
                mapping=mapping,
                offset=offset,
                stream_power=stream_power,
                baseline_sector_scale=baseline_sector,
                constrained_sectors=critical,
            )
            sparse_outcome = solve_continuous_l1(
                hard_stream,
                mapping,
                offset,
                base_decision,
                lower,
                upper,
                np.asarray(weights, dtype=np.float64),
                extra_system=budget_system,
            )
            selected_external = tuple(
                sorted(set(external) - set(critical))
            )
            selected_eess = tuple(
                sorted(set(eess_candidates) - set(critical))
            )
            if sparse_outcome.feasible:
                break

    if frozen_grid.feasible and frozen_grid.decision is not None:
        global_stream = SolverOutcome(
            status="FEASIBLE_BY_GLOBAL_FROZEN_GRID_SUBSET",
            feasible=True,
            optimal=False,
            decision=None,
            stream_scale=np.repeat(frozen_grid.decision, gain.shape[2]),
            objective=None,
            message=(
                "the global frozen sector grid is a subset of the global "
                "fixed-beam stream class; this is an oracle, not the selected "
                "distributed repair"
            ),
            maximum_constraint_excess=frozen_grid.maximum_constraint_excess,
            changed_variable_count=frozen_grid.changed_variable_count,
        )
    elif sparse_outcome.feasible and sparse_outcome.stream_scale is not None:
        global_stream = SolverOutcome(
            status="FEASIBLE_BY_SPARSE_STREAM_SUBSET",
            feasible=True,
            optimal=False,
            decision=None,
            stream_scale=np.asarray(sparse_outcome.stream_scale),
            objective=None,
            message="sparse local stream class is a subset of the global stream class",
            maximum_constraint_excess=sparse_outcome.maximum_constraint_excess,
            changed_variable_count=sparse_outcome.changed_variable_count,
        )
    elif local_grid.feasible and local_grid.stream_scale is not None:
        global_stream = SolverOutcome(
            status="FEASIBLE_BY_SPARSE_LOCAL_GRID_SUBSET",
            feasible=True,
            optimal=False,
            decision=None,
            stream_scale=np.asarray(local_grid.stream_scale),
            objective=None,
            message="sparse local sector grid is a subset of the global stream class",
            maximum_constraint_excess=local_grid.maximum_constraint_excess,
            changed_variable_count=local_grid.changed_variable_count,
        )
    else:
        global_stream = solve_continuous_l1(
            hard_stream,
            np.eye(gain.shape[1] * gain.shape[2], dtype=np.float64),
            np.zeros(gain.shape[1] * gain.shape[2], dtype=np.float64),
            baseline_stream,
            np.zeros_like(baseline_stream),
            np.ones_like(baseline_stream),
            np.maximum(stream_power.reshape(-1), 1e-12),
        )

    if baseline_hard_pass:
        chosen_class = "BASELINE_NOOP"
        chosen_stream = baseline_stream
    elif local_grid.feasible and local_grid.stream_scale is not None:
        chosen_class = "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR"
        chosen_stream = np.asarray(local_grid.stream_scale)
    elif sparse_outcome.feasible and sparse_outcome.stream_scale is not None:
        chosen_class = "SPARSE_LOCAL_STREAM_POWER_REPAIR"
        chosen_stream = np.asarray(sparse_outcome.stream_scale)
    else:
        chosen_class = "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND"
        chosen_stream = baseline_stream

    chosen_matrix = chosen_stream.reshape(gain.shape[1], gain.shape[2])
    audit = exact_audit(
        gain_user_sector_stream=gain,
        stream_scale=chosen_matrix,
        other_weighted_rate=state.other_weighted_rate,
        active_user=state.active_user,
        eligible_user=eligible_user,
        floors=floors,
        serving_bs=serving_bs,
        serving_stream=serving_stream,
        protected_noise_w=protected_noise_w,
        protected_weight=protected_weight,
        long_kappa_second_sector=long_kappa_second_sector,
        short_kappa_second_sector=short_kappa_second_sector,
        leakage_sector_stream=leakage,
        long_allowance_second=long_allowance_second,
        short_allowance_second=short_allowance_second,
        coupling_uplift_db=coupling_uplift_db,
    )
    success = (
        audit.floor_violation_count == 0
        and audit.long_violation_seconds == 0
        and audit.short_violation_seconds == 0
    )
    status = (
        "PASS_EXACT_FLOOR_AND_EESS_GATES"
        if success
        else "FAIL_OR_INFEASIBLE_REVIEW_REQUIRED"
    )
    sector_equivalent = np.empty(gain.shape[1], dtype=np.float64)
    for sector in range(gain.shape[1]):
        weights = stream_power[sector]
        denominator = float(np.sum(weights))
        sector_equivalent[sector] = (
            float(np.sum(weights * chosen_matrix[sector])) / denominator
            if denominator > 0.0
            else 0.0
        )
    return RepairChoice(
        status=status,
        chosen_action_class=chosen_class,
        stream_scale=chosen_matrix,
        sector_scale_equivalent=sector_equivalent,
        continuous_sector=continuous_sector,
        frozen_grid_sector=frozen_grid,
        local_frozen_grid_sector=local_grid,
        sparse_stream=sparse_outcome,
        global_stream_oracle=global_stream,
        exact_audit=audit,
        mutable_sectors=tuple(
            sorted(set(critical) | set(selected_external) | set(selected_eess))
        ),
        critical_serving_sectors=critical,
        top_external_sectors=selected_external,
        top_eess_sectors=selected_eess,
        claim_boundary=(
            "EXCLUDED_SEED_DIAGNOSTIC_FIXED_MODE_FIXED_BEAM_SPARSE_LOCAL_"
            "MAX_TWO_EXTERNAL_PER_VIOLATING_USER_MAX_TWO_EESS_SECTORS_"
            "NOT_CONFIRMATORY_NOT_CALIBRATION_NOT_REGULATORY_COMPLIANCE"
        ),
    )
