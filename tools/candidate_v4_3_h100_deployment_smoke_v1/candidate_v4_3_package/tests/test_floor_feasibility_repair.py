from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pytest

from fr3_cbf.floor_feasibility_repair import (
    EESS_VERIFICATION_TOLERANCE,
    FLOOR_COMPARISON_TOLERANCE,
    LinearSystem,
    SOLVER_CONSTRAINT_RESERVE,
    SOLVER_DUAL_FEASIBILITY_TOLERANCE,
    SOLVER_PRIMAL_FEASIBILITY_TOLERANCE,
    combine_systems,
    eess_system_for_stream_scales,
    exact_eess_ratio_from_stream_scale,
    exact_rates_from_stream_scale,
    floor_system_for_stream_scales,
    local_sector_power_budget_system,
    optimistic_single_user_upper_bound,
    repair_interval,
    sector_mapping,
    solve_continuous_l1,
    solve_frozen_sector_grid,
    sparse_hybrid_mapping,
    stream_power_envelopes,
)


@dataclass
class State:
    amp_perpendicular: np.ndarray
    amp_pol1: np.ndarray
    amp_pol2: np.ndarray
    other_weighted_rate: np.ndarray
    active_user: np.ndarray
    nominal_total_rate: np.ndarray


@dataclass
class Matrices:
    perpendicular: np.ndarray
    polarization_1: np.ndarray
    polarization_2: np.ndarray


def _floor_system(gain: np.ndarray, floor: float) -> LinearSystem:
    users = gain.shape[0]
    return floor_system_for_stream_scales(
        gain,
        np.zeros(users),
        np.ones(users, dtype=bool),
        np.ones(users, dtype=bool),
        np.full(users, floor),
        np.zeros(users, dtype=np.int64),
        np.zeros(users, dtype=np.int64),
        protected_noise_w=0.1,
        protected_weight=1.0,
    )


def test_floor_linearization_matches_exact_rate_for_random_scales() -> None:
    rng = np.random.default_rng(7)
    gain = np.array([[[2.0, 0.6], [0.5, 0.2]]], dtype=float)
    floor = 1.1
    system = _floor_system(gain, floor)
    assert system.a_ub.shape == (1, 4)
    for _ in range(250):
        scale = rng.random((2, 2))
        rate, _ = exact_rates_from_stream_scale(
            gain,
            scale,
            np.zeros(1),
            np.ones(1, dtype=bool),
            np.array([0]),
            np.array([0]),
            0.1,
            1.0,
        )
        linear_feasible = bool(
            np.all(system.a_ub @ scale.reshape(-1) <= system.b_ub + 1e-11)
        )
        exact_feasible = bool(rate[0] >= floor - 1e-11)
        assert linear_feasible == exact_feasible


def test_external_interferer_sector_backoff_is_feasible() -> None:
    # No same-sector interfering stream: the only defect is an external sector.
    gain = np.array([[[1.0, 0.0], [8.0, 0.0]]], dtype=float)
    floor = _floor_system(gain, 1.0)
    mapping = sector_mapping(2, 2)
    outcome = solve_continuous_l1(
        floor,
        mapping,
        np.zeros(4),
        np.ones(2),
        np.zeros(2),
        np.ones(2),
    )
    assert outcome.feasible
    assert outcome.decision is not None
    assert outcome.decision[0] > 0.99
    assert outcome.decision[1] < 0.2
    rate, _ = exact_rates_from_stream_scale(
        gain,
        np.repeat(outcome.decision, 2).reshape(2, 2),
        np.zeros(1),
        np.ones(1, dtype=bool),
        np.array([0]),
        np.array([0]),
        0.1,
        1.0,
    )
    assert rate[0] >= 1.0 - 1e-10


def test_stream_redistribution_repairs_when_any_sector_scalar_is_infeasible() -> None:
    # Sector-wide scaling cannot improve desired/intra-sector-interference ratio
    # enough, but physical-envelope-bounded stream redistribution can.
    gain = np.array([[[1.0, 1.0]]], dtype=float)
    floor = _floor_system(gain, 1.5)
    sector_outcome = solve_continuous_l1(
        floor,
        sector_mapping(1, 2),
        np.zeros(2),
        np.array([0.5]),
        np.zeros(1),
        np.ones(1),
    )
    assert not sector_outcome.feasible
    mapping, offset, baseline, _ = sparse_hybrid_mapping(
        np.array([0.5]), [0], [], stream_count=2
    )
    budget = local_sector_power_budget_system(
        mapping=mapping,
        offset=offset,
        actual_stream_power=np.ones((1, 2)),
        envelope_stream_power=np.ones((1, 2)),
        baseline_sector_scale=np.array([10.0 ** (-3.0 / 10.0)]),
        constrained_sectors=[0],
    )
    stream_outcome = solve_continuous_l1(
        floor,
        mapping,
        offset,
        baseline,
        np.zeros(2),
        np.ones(2),
        extra_system=budget,
    )
    assert stream_outcome.feasible
    scale = np.asarray(stream_outcome.stream_scale).reshape(1, 2)
    assert scale.sum() <= 1.0 + 1e-10
    assert scale[0, 0] > scale[0, 1]
    rate, _ = exact_rates_from_stream_scale(
        gain,
        scale,
        np.zeros(1),
        np.ones(1, dtype=bool),
        np.array([0]),
        np.array([0]),
        0.1,
        1.0,
    )
    assert rate[0] >= 1.5 - 1e-10


def test_local_power_budget_rejects_added_sector_power() -> None:
    mapping, offset, baseline, _ = sparse_hybrid_mapping(
        np.array([0.4]), [0], [], stream_count=2
    )
    budget = local_sector_power_budget_system(
        mapping=mapping,
        offset=offset,
        actual_stream_power=np.array([[2.0, 1.0]]),
        envelope_stream_power=np.array([[2.0, 1.0]]),
        baseline_sector_scale=np.array([0.4]),
        constrained_sectors=[0],
    )
    assert np.all(budget.a_ub @ baseline <= budget.b_ub + 1e-12)
    added = np.array([1.0, 1.0])
    assert np.any(budget.a_ub @ added > budget.b_ub + 1e-12)


def test_q0_nominal_power_envelope_dominates_nonnegative_mode_attenuation() -> None:
    matrices = Matrices(
        perpendicular=np.array([[[1.0], [0.0]]], dtype=complex),
        polarization_1=np.array([[[0.0], [1.0]]], dtype=complex),
        polarization_2=np.zeros((1, 2, 1), dtype=complex),
    )
    actual, nominal = stream_power_envelopes(
        matrices, np.array([[6.020599913279624, 0.0]])
    )
    assert actual.shape == nominal.shape == (1, 1)
    assert nominal[0, 0] == pytest.approx(2.0)
    assert actual[0, 0] == pytest.approx(1.25)
    assert actual[0, 0] < nominal[0, 0]


def test_q0_envelope_can_repair_case_strict_post_mode_budget_proves_infeasible() -> None:
    gain = np.array([[[1.0, 1.0]]], dtype=float)
    floor = _floor_system(gain, 3.0)
    mapping, offset, baseline, _ = sparse_hybrid_mapping(
        np.array([10.0 ** (-3.0 / 10.0)]), [0], [], stream_count=2
    )
    actual = np.array([[0.9, 0.1]])
    nominal_q0 = np.ones((1, 2))
    strict = local_sector_power_budget_system(
        mapping=mapping,
        offset=offset,
        actual_stream_power=actual,
        envelope_stream_power=actual,
        baseline_sector_scale=np.array([10.0 ** (-3.0 / 10.0)]),
        constrained_sectors=[0],
        label_prefix="strict_post_mode_power_budget",
    )
    corrected = local_sector_power_budget_system(
        mapping=mapping,
        offset=offset,
        actual_stream_power=actual,
        envelope_stream_power=nominal_q0,
        baseline_sector_scale=np.array([10.0 ** (-3.0 / 10.0)]),
        constrained_sectors=[0],
    )
    strict_outcome = solve_continuous_l1(
        floor, mapping, offset, baseline, np.zeros(2), np.ones(2),
        extra_system=strict,
    )
    corrected_outcome = solve_continuous_l1(
        floor, mapping, offset, baseline, np.zeros(2), np.ones(2),
        extra_system=corrected,
    )
    assert strict_outcome.status == "INFEASIBLE"
    assert not strict_outcome.feasible
    assert corrected_outcome.feasible
    assert corrected_outcome.stream_scale is not None
    scale = np.asarray(corrected_outcome.stream_scale).reshape(1, 2)
    assert float(np.sum(actual * scale)) <= (
        10.0 ** (-3.0 / 10.0) * float(np.sum(nominal_q0)) + 1e-10
    )


def test_eess_linear_rows_match_exact_physical_second_ratios() -> None:
    leakage = np.array([[0.5, 0.2], [0.1, 0.4]])
    stream_scale = np.array([[0.7, 0.3], [0.2, 0.8]])
    long_kappa = np.array([[1.0, 2.0], [0.5, 1.5]])
    short_kappa = np.array([[2.0, 0.2], [0.1, 0.3]])
    long_allowance = np.array([4.0, 2.0])
    short_allowance = np.array([3.0, 1.0])
    uplift = 0.0
    system = eess_system_for_stream_scales(
        long_kappa,
        short_kappa,
        leakage,
        long_allowance,
        short_allowance,
        uplift,
    )
    lhs = system.a_ub @ stream_scale.reshape(-1)
    exact = np.concatenate(
        [
            exact_eess_ratio_from_stream_scale(
                long_kappa, leakage, stream_scale, long_allowance, uplift
            ),
            exact_eess_ratio_from_stream_scale(
                short_kappa, leakage, stream_scale, short_allowance, uplift
            ),
        ]
    )
    assert np.allclose(lhs, exact, rtol=0.0, atol=1e-13)
    assert np.allclose(system.b_ub, 1.0)


def test_frozen_sector_grid_returns_exact_grid_action() -> None:
    # x0 >= 0.5 and x0 + x1 <= 1.1.  The baseline [1,1] violates the second
    # row.  Grid 0,3,6 dB,mute has the exact feasible choice [1,0].
    system = LinearSystem(
        np.array([[-1.0, 0.0], [1.0, 1.0]]),
        np.array([-0.5, 1.1]),
        ("floor", "eess"),
    )
    outcome = solve_frozen_sector_grid(
        system,
        np.ones(2),
        [0.0, 3.0, 6.0, math.inf],
        time_limit_s=10.0,
    )
    assert outcome.feasible
    assert outcome.decision is not None
    grid = np.array([1.0, 10 ** (-0.3), 10 ** (-0.6), 0.0])
    for value in outcome.decision:
        assert np.min(np.abs(grid - value)) < 1e-12
    assert np.all(system.a_ub @ outcome.decision <= system.b_ub + 1e-9)


def test_optimistic_single_user_bound_certifies_fixed_beam_shortfall() -> None:
    bound = optimistic_single_user_upper_bound(
        user=0,
        gain_user_sector_stream=np.array([[[1e-4]]]),
        other_weighted_rate=np.array([0.0]),
        serving_bs=np.array([0]),
        serving_stream=np.array([0]),
        protected_noise_w=1.0,
        protected_weight=1.0,
        long_kappa_second_sector=np.array([[0.0]]),
        short_kappa_second_sector=np.array([[0.0]]),
        leakage_sector_stream=np.array([[0.0]]),
        long_allowance_second=np.array([1.0]),
        short_allowance_second=np.array([1.0]),
        coupling_uplift_db=3.0,
    )
    assert bound["optimistic_total_rate_bps_hz"] < 0.1
    assert bound["maximum_target_stream_scale"] == pytest.approx(1.0)


def test_repair_interval_uses_frozen_grid_for_external_interference() -> None:
    # One user, two 2-stream sectors.  Backing off only sector 1 is sufficient.
    state = State(
        amp_perpendicular=np.array([[[1.0, 0.0], [math.sqrt(8.0), 0.0]]]),
        amp_pol1=np.zeros((1, 2, 2)),
        amp_pol2=np.zeros((1, 2, 2)),
        other_weighted_rate=np.zeros(1),
        active_user=np.ones(1, dtype=bool),
        nominal_total_rate=np.array([1.5]),
    )
    matrices = Matrices(
        perpendicular=np.array(
            [
                [[0.05, 0.0], [0.0, 0.05]],
                [[0.05, 0.0], [0.0, 0.05]],
            ],
            dtype=complex,
        ),
        polarization_1=np.zeros((2, 2, 2), dtype=complex),
        polarization_2=np.zeros((2, 2, 2), dtype=complex),
    )
    choice = repair_interval(
        state=state,
        matrices=matrices,
        q_db=np.zeros((2, 2)),
        baseline_sector_scale=np.ones(2),
        eligible_user=np.ones(1, dtype=bool),
        floors=np.array([1.0]),
        serving_bs=np.array([0]),
        serving_stream=np.array([0]),
        protected_noise_w=0.1,
        protected_weight=1.0,
        steering_pol1=np.ones((2, 2), dtype=complex),
        steering_pol2=np.zeros((2, 2), dtype=complex),
        long_kappa_second_sector=np.ones((2, 2)),
        short_kappa_second_sector=np.ones((2, 2)),
        long_allowance_second=np.full(2, 100.0),
        short_allowance_second=np.full(2, 100.0),
        coupling_uplift_db=3.0,
        grid_backoff_db=[0.0, 3.0, 6.0, 9.0, 12.0, math.inf],
        grid_time_limit_s=10.0,
    )
    assert choice.status == "PASS_EXACT_FLOOR_AND_EESS_GATES"
    assert choice.chosen_action_class == "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR"
    assert choice.local_frozen_grid_sector.feasible
    assert choice.stream_scale[1, 0] < choice.stream_scale[0, 0]
    assert choice.exact_audit.floor_violation_count == 0


def test_repair_interval_uses_physical_envelope_bounded_local_stream_redistribution() -> None:
    state = State(
        amp_perpendicular=np.array([[[1.0, 1.0]]]),
        amp_pol1=np.zeros((1, 1, 2)),
        amp_pol2=np.zeros((1, 1, 2)),
        other_weighted_rate=np.zeros(1),
        active_user=np.ones(1, dtype=bool),
        nominal_total_rate=np.array([2.0]),
    )
    matrices = Matrices(
        perpendicular=np.array([[[1.0, 0.0], [0.0, 1.0]]], dtype=complex),
        polarization_1=np.zeros((1, 2, 2), dtype=complex),
        polarization_2=np.zeros((1, 2, 2), dtype=complex),
    )
    choice = repair_interval(
        state=state,
        matrices=matrices,
        q_db=np.zeros((1, 2)),
        baseline_sector_scale=np.array([10.0 ** (-3.0 / 10.0)]),
        eligible_user=np.ones(1, dtype=bool),
        floors=np.array([1.5]),
        serving_bs=np.array([0]),
        serving_stream=np.array([0]),
        protected_noise_w=0.1,
        protected_weight=1.0,
        steering_pol1=np.array([[0.01, 0.01]], dtype=complex),
        steering_pol2=np.zeros((1, 2), dtype=complex),
        long_kappa_second_sector=np.ones((1, 1)),
        short_kappa_second_sector=np.ones((1, 1)),
        long_allowance_second=np.array([100.0]),
        short_allowance_second=np.array([100.0]),
        coupling_uplift_db=3.0,
        grid_backoff_db=[0.0, 3.0, 6.0, 9.0, 12.0, math.inf],
        external_neighbourhood_sizes=[0],
        grid_time_limit_s=10.0,
    )
    assert choice.status == "PASS_EXACT_FLOOR_AND_EESS_GATES"
    assert choice.chosen_action_class == "SPARSE_LOCAL_STREAM_POWER_REPAIR"
    assert choice.strict_post_mode_sparse_stream.feasible
    assert choice.strict_post_mode_sparse_stream.status == (
        "OPTIMAL_CONTINUOUS_L1_CERTIFIED_RESERVE"
    )
    assert np.sum(choice.stream_scale[0]) <= 1.0 + 1e-9
    assert choice.stream_scale[0, 0] > choice.stream_scale[0, 1]


def test_q0_only_witness_is_diagnostic_and_not_deployed() -> None:
    baseline = 10.0 ** (-3.0 / 10.0)
    state = State(
        amp_perpendicular=np.array([[[1.0, 1.0]]]),
        amp_pol1=np.zeros((1, 1, 2)),
        amp_pol2=np.zeros((1, 1, 2)),
        other_weighted_rate=np.zeros(1),
        active_user=np.ones(1, dtype=bool),
        nominal_total_rate=np.array([3.5]),
    )
    perpendicular = np.zeros((1, 4, 2), dtype=complex)
    polarization_1 = np.zeros((1, 4, 2), dtype=complex)
    perpendicular[0, 0, 0] = math.sqrt(8.0 / 9.0)
    polarization_1[0, 1, 0] = math.sqrt(1.0 / 9.0)
    polarization_1[0, 2, 1] = 1.0
    matrices = Matrices(
        perpendicular=perpendicular,
        polarization_1=polarization_1,
        polarization_2=np.zeros((1, 4, 2), dtype=complex),
    )
    choice = repair_interval(
        state=state,
        matrices=matrices,
        q_db=np.array([[10.0, 0.0]]),
        baseline_sector_scale=np.array([baseline]),
        eligible_user=np.ones(1, dtype=bool),
        floors=np.array([3.0]),
        serving_bs=np.array([0]),
        serving_stream=np.array([0]),
        protected_noise_w=0.1,
        protected_weight=1.0,
        steering_pol1=np.zeros((1, 4), dtype=complex),
        steering_pol2=np.zeros((1, 4), dtype=complex),
        long_kappa_second_sector=np.zeros((1, 1)),
        short_kappa_second_sector=np.zeros((1, 1)),
        long_allowance_second=np.ones(1),
        short_allowance_second=np.ones(1),
        coupling_uplift_db=3.0,
        grid_backoff_db=[0.0, 3.0, 6.0, 9.0, 12.0, math.inf],
        external_neighbourhood_sizes=[0],
        eess_neighbourhood_size=0,
        grid_time_limit_s=10.0,
    )
    assert choice.status == "FAIL_OR_INFEASIBLE_REVIEW_REQUIRED"
    assert choice.chosen_action_class == "NO_FEASIBLE_DEPLOYABLE_ACTION_FOUND"
    assert not choice.strict_post_mode_sparse_stream.feasible
    assert choice.q0_nominal_envelope_sparse_stream.feasible
    actual, nominal_q0 = stream_power_envelopes(
        matrices, np.array([[10.0, 0.0]])
    )
    q0_scale = np.asarray(
        choice.q0_nominal_envelope_sparse_stream.stream_scale
    ).reshape(1, 2)
    q0_selected_power = float(np.sum(actual * q0_scale))
    assert q0_selected_power <= (
        baseline * float(np.sum(nominal_q0)) + 1e-10
    )
    assert q0_selected_power > baseline * float(np.sum(actual)) + 1e-6
    # The broader q=0 witness is retained only for diagnosis; the actual
    # selected action remains the reviewed baseline and therefore still fails.
    assert np.allclose(choice.stream_scale, baseline)
    assert choice.exact_audit.floor_violation_count == 1


def test_solver_reserve_creates_certified_interior_witness() -> None:
    system = LinearSystem(
        np.array([[-1.0]]),
        np.array([-0.5]),
        ("x_at_least_half",),
    )
    outcome = solve_continuous_l1(
        system,
        np.eye(1),
        np.zeros(1),
        np.zeros(1),
        np.zeros(1),
        np.ones(1),
        constraint_reserve=SOLVER_CONSTRAINT_RESERVE,
    )
    assert outcome.feasible
    assert outcome.status == "OPTIMAL_CONTINUOUS_L1_CERTIFIED_RESERVE"
    assert outcome.decision is not None
    assert outcome.decision[0] >= 0.5 + 0.5 * SOLVER_CONSTRAINT_RESERVE
    assert outcome.maximum_constraint_excess is not None
    assert outcome.maximum_constraint_excess < 0.0


def test_scientific_tolerances_are_unchanged_and_solver_is_tightened() -> None:
    assert FLOOR_COMPARISON_TOLERANCE == 1e-12
    assert EESS_VERIFICATION_TOLERANCE == 1e-10
    assert SOLVER_CONSTRAINT_RESERVE == 1e-8
    assert SOLVER_PRIMAL_FEASIBILITY_TOLERANCE == 1e-9
    assert SOLVER_DUAL_FEASIBILITY_TOLERANCE == 1e-9

def test_combined_floor_and_eess_system_preserves_hard_priority() -> None:
    gain = np.array([[[1.0], [2.0]]])
    floor = _floor_system(gain, 0.8)
    eess = LinearSystem(
        np.array([[0.1, 1.0]]),
        np.array([0.3]),
        ("eess",),
    )
    hard = combine_systems(floor, eess)
    outcome = solve_continuous_l1(
        hard,
        np.eye(2),
        np.zeros(2),
        np.ones(2),
        np.zeros(2),
        np.ones(2),
    )
    assert outcome.feasible
    assert outcome.decision is not None
    assert np.all(hard.a_ub @ outcome.decision <= hard.b_ub + 1e-9)


def test_repair_interval_repairs_eess_only_failure_with_bounded_scalar_backoff() -> None:
    state = State(
        amp_perpendicular=np.array([[[1.0], [0.0], [0.0]]]),
        amp_pol1=np.zeros((1, 3, 1)),
        amp_pol2=np.zeros((1, 3, 1)),
        other_weighted_rate=np.zeros(1),
        active_user=np.ones(1, dtype=bool),
        nominal_total_rate=np.array([2.0]),
    )
    matrices = Matrices(
        perpendicular=np.array([[[0.0]], [[1.0]], [[0.1]]], dtype=complex),
        polarization_1=np.zeros((3, 1, 1), dtype=complex),
        polarization_2=np.zeros((3, 1, 1), dtype=complex),
    )
    choice = repair_interval(
        state=state,
        matrices=matrices,
        q_db=np.zeros((3, 2)),
        baseline_sector_scale=np.ones(3),
        eligible_user=np.ones(1, dtype=bool),
        floors=np.array([0.5]),
        serving_bs=np.array([0]),
        serving_stream=np.array([0]),
        protected_noise_w=0.1,
        protected_weight=1.0,
        steering_pol1=np.ones((3, 1), dtype=complex),
        steering_pol2=np.zeros((3, 1), dtype=complex),
        long_kappa_second_sector=np.ones((1, 3)),
        short_kappa_second_sector=np.ones((1, 3)),
        long_allowance_second=np.array([0.6]),
        short_allowance_second=np.array([0.6]),
        coupling_uplift_db=0.0,
        grid_backoff_db=[0.0, 3.0, 6.0, 9.0, 12.0, math.inf],
        external_neighbourhood_sizes=[0],
        eess_neighbourhood_size=1,
        grid_time_limit_s=10.0,
    )
    assert choice.status == "PASS_EXACT_FLOOR_AND_EESS_GATES"
    assert choice.chosen_action_class == "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR"
    assert choice.critical_serving_sectors == tuple()
    assert choice.top_external_sectors == tuple()
    assert choice.top_eess_sectors == (1,)
    assert choice.mutable_sectors == (1,)
    assert choice.stream_scale[1, 0] < 1.0
    assert choice.stream_scale[0, 0] == pytest.approx(1.0)
    assert choice.exact_audit.floor_violation_count == 0
    assert choice.exact_audit.long_violation_seconds == 0
    assert choice.exact_audit.short_violation_seconds == 0


def test_deployable_neighbourhood_bounds_are_hard_contracts() -> None:
    state = State(
        amp_perpendicular=np.ones((1, 1, 1)),
        amp_pol1=np.zeros((1, 1, 1)),
        amp_pol2=np.zeros((1, 1, 1)),
        other_weighted_rate=np.zeros(1),
        active_user=np.ones(1, dtype=bool),
        nominal_total_rate=np.ones(1),
    )
    matrices = Matrices(
        perpendicular=np.ones((1, 1, 1), dtype=complex),
        polarization_1=np.zeros((1, 1, 1), dtype=complex),
        polarization_2=np.zeros((1, 1, 1), dtype=complex),
    )
    common = dict(
        state=state,
        matrices=matrices,
        q_db=np.zeros((1, 2)),
        baseline_sector_scale=np.ones(1),
        eligible_user=np.ones(1, dtype=bool),
        floors=np.array([0.1]),
        serving_bs=np.array([0]),
        serving_stream=np.array([0]),
        protected_noise_w=0.1,
        protected_weight=1.0,
        steering_pol1=np.ones((1, 1), dtype=complex),
        steering_pol2=np.zeros((1, 1), dtype=complex),
        long_kappa_second_sector=np.zeros((1, 1)),
        short_kappa_second_sector=np.zeros((1, 1)),
        long_allowance_second=np.ones(1),
        short_allowance_second=np.ones(1),
        coupling_uplift_db=3.0,
        grid_backoff_db=[0.0, math.inf],
    )
    with pytest.raises(ValueError, match="external neighbourhood"):
        repair_interval(**common, external_neighbourhood_sizes=[3])
    with pytest.raises(ValueError, match="EESS neighbourhood"):
        repair_interval(**common, eess_neighbourhood_size=3)


def test_floor_repair_can_release_eess_headroom_from_noninterfering_sector() -> None:
    baseline_serving = 10.0 ** (-3.0 / 10.0)
    state = State(
        amp_perpendicular=np.array([[[1.0], [0.0], [0.0]]]),
        amp_pol1=np.zeros((1, 3, 1)),
        amp_pol2=np.zeros((1, 3, 1)),
        other_weighted_rate=np.zeros(1),
        active_user=np.ones(1, dtype=bool),
        nominal_total_rate=np.array([3.5]),
    )
    matrices = Matrices(
        perpendicular=np.array(
            [[[math.sqrt(0.4)]], [[math.sqrt(0.5)]], [[0.0]]],
            dtype=complex,
        ),
        polarization_1=np.zeros((3, 1, 1), dtype=complex),
        polarization_2=np.zeros((3, 1, 1), dtype=complex),
    )
    choice = repair_interval(
        state=state,
        matrices=matrices,
        q_db=np.zeros((3, 2)),
        baseline_sector_scale=np.array([baseline_serving, 1.0, 1.0]),
        eligible_user=np.ones(1, dtype=bool),
        floors=np.array([3.0]),
        serving_bs=np.array([0]),
        serving_stream=np.array([0]),
        protected_noise_w=0.1,
        protected_weight=1.0,
        steering_pol1=np.ones((3, 1), dtype=complex),
        steering_pol2=np.zeros((3, 1), dtype=complex),
        long_kappa_second_sector=np.ones((1, 3)),
        short_kappa_second_sector=np.ones((1, 3)),
        long_allowance_second=np.array([0.75]),
        short_allowance_second=np.array([0.75]),
        coupling_uplift_db=0.0,
        grid_backoff_db=[0.0, 3.0, 6.0, 9.0, 12.0, math.inf],
        external_neighbourhood_sizes=[0],
        eess_neighbourhood_size=1,
        grid_time_limit_s=10.0,
    )
    assert choice.status == "PASS_EXACT_FLOOR_AND_EESS_GATES"
    assert choice.chosen_action_class == "SPARSE_LOCAL_FROZEN_GRID_SECTOR_REPAIR"
    assert choice.critical_serving_sectors == (0,)
    assert choice.top_external_sectors == tuple()
    assert choice.top_eess_sectors == (1,)
    assert choice.mutable_sectors == (0, 1)
    assert choice.stream_scale[0, 0] > baseline_serving
    assert choice.stream_scale[1, 0] < 1.0
    assert choice.exact_audit.floor_violation_count == 0
    assert choice.exact_audit.long_violation_seconds == 0
    assert choice.exact_audit.short_violation_seconds == 0
