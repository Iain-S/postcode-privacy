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
    assert result.p95 >= result.achieved


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
