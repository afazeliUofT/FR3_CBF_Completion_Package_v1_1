from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np


@dataclass(frozen=True)
class BeamFilterResult:
    status: str
    beamformers: np.ndarray | None
    slack: np.ndarray | None
    objective_value: float | None
    solve_time_s: float
    solver_name: str | None


def _psd_sqrt(matrix: np.ndarray, tolerance: float = 1e-10) -> np.ndarray:
    matrix = 0.5 * (matrix + matrix.conj().T)
    values, vectors = np.linalg.eigh(matrix)
    if values.min() < -tolerance:
        raise ValueError(f"Coupling matrix is not PSD; minimum eigenvalue={values.min()}")
    values = np.maximum(values, 0.0)
    # L^H L = R, so ||L W||_F^2 = tr(W^H R W).
    return np.diag(np.sqrt(values)) @ vectors.conj().T


def solve_minimal_deviation_filter(
    nominal_beamformers: np.ndarray,
    previous_beamformers: np.ndarray,
    coupling_scenarios: np.ndarray,
    thresholds: np.ndarray,
    tone_weights: np.ndarray,
    power_limits: np.ndarray,
    slew_limits: np.ndarray,
    slack_penalty: float = 1e8,
    solver: str | None = None,
    solver_options: dict[str, Any] | None = None,
) -> BeamFilterResult:
    """Solve the finite-scenario fully digital beam-space safety filter.

    Shapes
    ------
    nominal/previous: [B,T,M,K]
    coupling_scenarios: [L,S,B,T,M,M]
    thresholds: [L]
    tone_weights: [T]
    power_limits: [B]
    slew_limits: [B]

    The result is a small-network benchmark. Hybrid arrays require factorization and
    re-verification of the transmitted composite precoder.
    """
    try:
        import cvxpy as cp
    except ImportError as exc:
        raise ImportError("Install requirements-full.txt to use the beam-space CVXPY benchmark") from exc

    w_nom = np.asarray(nominal_beamformers, dtype=np.complex128)
    w_prev = np.asarray(previous_beamformers, dtype=np.complex128)
    r = np.asarray(coupling_scenarios, dtype=np.complex128)
    c = np.asarray(thresholds, dtype=float)
    eta = np.asarray(tone_weights, dtype=float)
    pmax = np.asarray(power_limits, dtype=float)
    delta = np.asarray(slew_limits, dtype=float)
    if w_nom.shape != w_prev.shape or w_nom.ndim != 4:
        raise ValueError("nominal and previous beamformers must have matching [B,T,M,K] shape")
    b_count, t_count, m_count, k_count = w_nom.shape
    if r.ndim != 6 or r.shape[2:] != (b_count, t_count, m_count, m_count):
        raise ValueError("coupling_scenarios must have shape [L,S,B,T,M,M]")
    l_count, s_count = r.shape[:2]
    if c.shape != (l_count,) or eta.shape != (t_count,) or pmax.shape != (b_count,) or delta.shape != (b_count,):
        raise ValueError("threshold/tone/power/slew dimensions do not match")
    if np.any(c <= 0) or np.any(pmax <= 0) or np.any(delta < 0) or np.any(eta < 0):
        raise ValueError("invalid nonpositive limits or negative weights")

    w_vars = [[cp.Variable((m_count, k_count), complex=True) for _ in range(t_count)] for _ in range(b_count)]
    slack = cp.Variable(l_count, nonneg=True)
    objective_terms = []
    constraints = []
    for b in range(b_count):
        power_terms = []
        slew_terms = []
        for t in range(t_count):
            objective_terms.append(cp.sum_squares(cp.abs(w_vars[b][t] - w_nom[b, t])))
            power_terms.append(eta[t] * cp.sum_squares(cp.abs(w_vars[b][t])))
            slew_terms.append(cp.sum_squares(cp.abs(w_vars[b][t] - w_prev[b, t])))
        constraints.append(cp.sum(power_terms) <= pmax[b])
        constraints.append(cp.sum(slew_terms) <= delta[b] ** 2)

    square_roots: dict[tuple[int, int, int, int], np.ndarray] = {}
    for l in range(l_count):
        for s in range(s_count):
            terms = []
            for b in range(b_count):
                for t in range(t_count):
                    key = (l, s, b, t)
                    square_roots[key] = _psd_sqrt(r[l, s, b, t])
                    terms.append(eta[t] * cp.sum_squares(cp.abs(square_roots[key] @ w_vars[b][t])))
            constraints.append(cp.sum(terms) <= c[l] + slack[l])

    problem = cp.Problem(cp.Minimize(cp.sum(objective_terms) + slack_penalty * cp.sum(slack)), constraints)
    start = perf_counter()
    solve_kwargs = dict(solver_options or {})
    if solver:
        solve_kwargs["solver"] = solver
    problem.solve(**solve_kwargs)
    elapsed = perf_counter() - start
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
        return BeamFilterResult(problem.status, None, None, None, elapsed, solver)
    solution = np.empty_like(w_nom)
    for b in range(b_count):
        for t in range(t_count):
            solution[b, t] = w_vars[b][t].value
    return BeamFilterResult(
        status=problem.status,
        beamformers=solution,
        slack=np.asarray(slack.value, dtype=float),
        objective_value=float(problem.value),
        solve_time_s=elapsed,
        solver_name=solver,
    )
