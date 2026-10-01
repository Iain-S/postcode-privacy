"""The mechanism's output distribution, checked exactly."""

import numpy as np
import pytest

from postcode_privacy._reference import distribution as reference_distribution
from postcode_privacy.graph.adjacency import Adjacency
from postcode_privacy.mechanism.hop import PriorError, distribution

PATH_EDGES = np.array([[0, 1], [1, 2], [2, 3]], dtype=np.int64)
PATH_DENSE = np.array(
    [[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0]], dtype=bool
)


def path_adjacency() -> Adjacency:
    return Adjacency.from_edges(PATH_EDGES, n_nodes=4)


def test_probabilities_sum_to_one() -> None:
    dist = distribution(
        path_adjacency(), np.ones(4, dtype=np.int64), source=0, epsilon=1.0, radius=3
    )

    assert dist.as_array(4).sum() == pytest.approx(1.0)


def test_probability_decays_with_hop_distance() -> None:
    dist = distribution(
        path_adjacency(), np.ones(4, dtype=np.int64), source=0, epsilon=1.0, radius=9
    )

    probabilities = dist.as_array(4)
    assert probabilities[0] > probabilities[1] > probabilities[2] > probabilities[3]


def test_no_node_is_ever_unreachable() -> None:
    # Capping the metric rather than the support is what keeps this true, and
    # keeping it true is what keeps the guarantee pure rather than approximate.
    dist = distribution(
        path_adjacency(), np.ones(4, dtype=np.int64), source=0, epsilon=5.0, radius=1
    )

    assert (dist.as_array(4) > 0).all()


@pytest.mark.parametrize("epsilon", [0.3, 1.0, 2.5])
@pytest.mark.parametrize("radius", [1, 2, 5])
@pytest.mark.parametrize("source", [0, 1, 3])
def test_it_matches_the_naive_reference(
    epsilon: float, radius: int, source: int
) -> None:
    # The differential test: the shell-decomposed integer implementation against
    # a dense float one written to be too simple to be wrong.
    prior = np.array([3, 1, 4, 1], dtype=np.int64)

    ours = distribution(
        Adjacency.from_edges(PATH_EDGES, n_nodes=4),
        prior,
        source=source,
        epsilon=epsilon,
        radius=radius,
    ).as_array(4)
    theirs = reference_distribution(
        PATH_DENSE,
        prior.astype(np.float64),
        epsilon=epsilon,
        radius=radius,
        source=source,
    )

    np.testing.assert_allclose(ours, theirs, rtol=1e-12)


def test_a_zero_prior_is_rejected() -> None:
    # A node that can never be produced cannot hide anyone in it.
    with pytest.raises(PriorError):
        distribution(
            path_adjacency(),
            np.array([1, 0, 1, 1], dtype=np.int64),
            source=0,
            epsilon=1.0,
            radius=3,
        )


@pytest.mark.parametrize("radius", [1, 2, 5])
@pytest.mark.parametrize("source", [0, 2])
def test_the_integer_weights_agree_with_the_probabilities(
    radius: int, source: int
) -> None:
    # as_array recomputes probabilities from scratch, while the sampler will use
    # the integer shell weights. Nothing otherwise forces the two to agree, so a
    # fault in the weights would be invisible to every test that inspects
    # probabilities -- we would be testing one path and shipping another.
    prior = np.array([3, 1, 4, 1], dtype=np.int64)
    dist = distribution(
        Adjacency.from_edges(PATH_EDGES, n_nodes=4),
        prior,
        source=source,
        epsilon=1.0,
        radius=radius,
    )
    probabilities = dist.as_array(4)
    total = dist.total_weight

    for hop, nodes in enumerate(dist.shell_nodes):
        assert probabilities[nodes].sum() == pytest.approx(
            dist.shell_weights[hop] / total
        ), f"shell {hop} weight disagrees with its probabilities"

    in_a_shell = np.concatenate(dist.shell_nodes) if dist.shell_nodes else []
    tail = np.setdiff1d(np.arange(4), in_a_shell)
    assert probabilities[tail].sum() == pytest.approx(dist.tail_weight / total)
    assert dist.teleport_probability == pytest.approx(probabilities[tail].sum())
