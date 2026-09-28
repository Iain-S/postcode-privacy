"""Tests for the naive reference implementation.

The reference exists to be an oracle: it is deliberately slow and obvious so that
the optimised implementation can be differentially tested against something too
simple to be wrong. These tests therefore check it against hand-computed values,
never against the real implementation.
"""

import numpy as np

from postcode_privacy._reference import distribution, hop_distances


def test_hop_distances_on_a_path_graph() -> None:
    # 0 -- 1 -- 2
    adjacency = np.array(
        [
            [0, 1, 0],
            [1, 0, 1],
            [0, 1, 0],
        ],
        dtype=bool,
    )

    distances = hop_distances(adjacency)

    expected = np.array(
        [
            [0, 1, 2],
            [1, 0, 1],
            [2, 1, 0],
        ],
        dtype=float,
    )
    np.testing.assert_array_equal(distances, expected)


def test_hop_distances_are_infinite_between_disconnected_components() -> None:
    # 0 -- 1    2   (2 is an island: the graph builder has not bridged it yet)
    adjacency = np.array(
        [
            [0, 1, 0],
            [1, 0, 0],
            [0, 0, 0],
        ],
        dtype=bool,
    )

    distances = hop_distances(adjacency)

    assert distances[0, 2] == np.inf
    assert distances[2, 0] == np.inf
    assert distances[2, 2] == 0.0


def test_distribution_weights_decay_by_hop_distance() -> None:
    # 0 -- 1, uniform prior. With epsilon = 2*ln(2) the exponential term
    # exp(-epsilon*d/2) is exactly 1/2 at one hop, so the weights are 1 and 1/2
    # and the normalised probabilities are exactly 2/3 and 1/3.
    adjacency = np.array([[0, 1], [1, 0]], dtype=bool)
    prior = np.array([1.0, 1.0])

    probabilities = distribution(
        adjacency, prior, epsilon=2 * np.log(2), radius=10, source=0
    )

    np.testing.assert_allclose(probabilities, [2 / 3, 1 / 3])


def test_radius_caps_the_metric_rather_than_truncating_the_support() -> None:
    # 0 -- 1 -- 2 -- 3 with radius 1: nodes 2 and 3 are beyond the cap, so they
    # share node 1's weight rather than dropping to zero. Support truncation --
    # the obvious alternative -- would give them zero and break pure DP.
    adjacency = np.array(
        [
            [0, 1, 0, 0],
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
        ],
        dtype=bool,
    )
    prior = np.ones(4)

    probabilities = distribution(adjacency, prior, epsilon=1.0, radius=1, source=0)

    assert (probabilities > 0).all()
    np.testing.assert_allclose(probabilities[1], probabilities[2])
    np.testing.assert_allclose(probabilities[1], probabilities[3])
    assert probabilities[0] > probabilities[1]
