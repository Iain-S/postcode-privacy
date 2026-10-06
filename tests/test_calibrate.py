"""Measuring what an epsilon does, and solving for one that meets a target."""

import numpy as np
import pytest

from postcode_privacy import HopMechanism, PostcodeGraph
from postcode_privacy.mechanism.calibrate import (
    TARGETS,
    UnknownTargetError,
    calibrate,
    displacement_summary,
)

N = 40
SPACING_M = 1000


def line() -> PostcodeGraph:
    """Postcodes a kilometre apart in a row, so distances are known exactly."""
    return PostcodeGraph.from_edges(
        postcodes=np.array([f"A{i:03d} 1AA" for i in range(N)]),
        edges=np.array([[i, i + 1] for i in range(N - 1)], dtype=np.int64),
        prior=np.ones(N, dtype=np.int64),
        eastings=np.arange(N, dtype=np.int64) * SPACING_M,
        northings=np.zeros(N, dtype=np.int64),
    )


def test_a_large_epsilon_barely_moves_anyone() -> None:
    summary = displacement_summary(HopMechanism(line(), epsilon=20.0), "A020 1AA")

    assert summary.median_km == 0.0
    assert summary.self_probability > 0.99


def test_a_smaller_epsilon_moves_people_further() -> None:
    # The relationship the whole calibration rests on. If it did not hold
    # monotonically, solving for a target would be meaningless.
    distances = [
        displacement_summary(HopMechanism(line(), epsilon=eps), "A020 1AA").median_km
        for eps in (4.0, 2.0, 1.0, 0.5)
    ]

    assert distances == sorted(distances)


def test_displacement_is_reported_separately_from_teleporting() -> None:
    # Mixing them would hide a too-small radius: a handful of country-wide jumps
    # would drag a mean upwards and look like ordinary spread.
    summary = displacement_summary(HopMechanism(line(), epsilon=1.0), "A020 1AA")

    assert summary.median_km >= 0
    assert 0 <= summary.teleport_probability <= 1
    assert summary.ball_size > 0


def test_calibrate_finds_an_epsilon_that_hits_a_displacement_target() -> None:
    result = calibrate(line(), target="median-displacement-km", value=3.0)

    assert result.achieved == pytest.approx(3.0, abs=1.0)
    assert result.epsilon > 0


def test_calibrate_finds_an_epsilon_for_a_self_probability_target() -> None:
    # The most directly interpretable privacy question a user can ask: how often
    # is my true postcode simply handed back?
    result = calibrate(line(), target="max-self-probability", value=0.05)

    assert result.achieved <= 0.05 + 1e-6
    mechanism = HopMechanism(line(), epsilon=result.epsilon)
    assert mechanism.distribution("A020 1AA").self_probability <= 0.06


def test_an_unknown_target_lists_the_ones_that_exist() -> None:
    with pytest.raises(UnknownTargetError) as caught:
        calibrate(line(), target="vibes", value=1.0)

    for name in TARGETS:
        assert name in str(caught.value)


def test_calibration_reports_the_spread_not_just_the_median() -> None:
    # A single national number hides exactly the disparity this design exists
    # to fix, so the result carries the spread it was solved against.
    result = calibrate(line(), target="median-displacement-km", value=3.0)

    assert result.sample_size > 0
    # For a displacement target the spread is the p95, which sits above the
    # median being calibrated against.
    assert result.spread >= result.achieved


def test_every_shell_contributes_to_the_measured_displacement() -> None:
    # Guards the pairing of shells with their weights. `powers` holds one more
    # entry than there are shells -- the floor applied beyond the cap -- so a
    # lenient zip would quietly drop a shell and understate how far people move.
    mechanism = HopMechanism(line(), epsilon=1.0)
    distribution = mechanism.distribution("A020 1AA")
    summary = displacement_summary(mechanism, "A020 1AA")

    furthest_shell_km = (N - 1) * SPACING_M / 1000
    assert len(distribution.powers) == len(distribution.shell_nodes) + 1
    assert 0 < summary.p95_km <= furthest_shell_km


def test_an_unreachable_target_is_reported_as_such() -> None:
    # Asking for something the mechanism cannot deliver must not be answered
    # with a bracket endpoint dressed up as a solution.
    result = calibrate(line(), target="median-displacement-km", value=10_000.0)

    assert result.reached is False
    assert result.achieved < 10_000.0


def test_a_reachable_target_is_marked_reached() -> None:
    result = calibrate(line(), target="max-self-probability", value=0.05)

    assert result.reached is True


def heterogeneous() -> PostcodeGraph:
    """A graph where self-probability varies a lot between postcodes.

    A dense clique beside a sparse tail: nodes in the clique have many near
    neighbours and low self-probability, the tail node has few and high. On a
    uniform line the median and the maximum nearly coincide, which is why the
    original bug survived its tests.
    """
    n = 12
    edges = [[i, j] for i in range(8) for j in range(i + 1, 8)]
    edges += [[7, 8], [8, 9], [9, 10], [10, 11]]
    return PostcodeGraph.from_edges(
        postcodes=np.array([f"A{i:03d} 1AA" for i in range(n)]),
        edges=np.array(edges, dtype=np.int64),
        prior=np.ones(n, dtype=np.int64),
        eastings=np.arange(n, dtype=np.int64) * 100,
        northings=np.zeros(n, dtype=np.int64),
    )


def test_the_graph_really_is_heterogeneous() -> None:
    # Guards the fixture: if median and maximum coincide the test below cannot
    # tell the two statistics apart, and would pass against the bug.
    mechanism = HopMechanism(heterogeneous(), epsilon=1.0)
    values = [
        mechanism.distribution(str(p)).self_probability
        for p in heterogeneous().postcodes
    ]

    assert np.max(values) > 1.5 * np.median(values)


def test_max_self_probability_bounds_the_whole_sample_not_its_middle() -> None:
    # The target is a privacy target. Meeting it at the median means half the
    # sample exceeds the number the user asked for.
    graph = heterogeneous()
    postcodes = [str(p) for p in graph.postcodes]

    # Above 1/12, the floor a twelve-node graph with a uniform prior imposes
    # however small epsilon becomes.
    target = 0.15
    result = calibrate(
        graph,
        target="max-self-probability",
        value=target,
        sample_size=len(postcodes),
    )

    assert result.reached is True
    mechanism = HopMechanism(graph, epsilon=result.epsilon)
    achieved = [mechanism.distribution(p).self_probability for p in postcodes]
    assert max(achieved) <= target + 1e-9
    # And the median is well below it, which is exactly what the old behaviour
    # would have calibrated against instead.
    assert float(np.median(achieved)) < target


def test_a_self_probability_target_below_the_graphs_floor_is_unreachable() -> None:
    # A twelve-node graph with a uniform prior cannot put self-probability below
    # 1/12 at any epsilon. Saying so beats returning the bracket endpoint.
    result = calibrate(heterogeneous(), target="max-self-probability", value=0.01)

    assert result.reached is False
    assert result.achieved > 0.01
