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


def test_a_distribution_costs_memory_in_proportion_to_its_ball() -> None:
    """A distribution must not carry a copy of anything country-sized.

    Distributions are cached per distinct postcode, so any array scaling with the
    whole graph is paid again for every postcode in the dataset. On the real
    graph one national-scale array costs 14 MB, which a thousand distinct
    postcodes turns into 16 GB. Whatever is shared across distributions belongs
    to the graph, not to each distribution.
    """
    n_nodes = 400
    edges = np.array([[i, i + 1] for i in range(n_nodes - 1)], dtype=np.int64)
    graph = Adjacency.from_edges(edges, n_nodes=n_nodes)
    prior = np.ones(n_nodes, dtype=np.int64)

    dist = distribution(graph, prior, source=0, epsilon=2.0, radius=4)

    ball_size = len(dist.ball)
    assert ball_size < n_nodes, "the ball must be smaller than the graph here"

    owned = [
        value
        for name, value in vars(dist).items()
        if isinstance(value, np.ndarray) and name != "prior"
    ]
    for array in owned:
        assert len(array) <= ball_size, (
            f"a distribution owns an array of length {len(array)} but its ball "
            f"holds only {ball_size} nodes"
        )


def test_the_probability_of_one_node_matches_the_full_array() -> None:
    # A single-node lookup exists because the adversary code needs one entry per
    # candidate, and allocating a national vector per candidate is not viable.
    # It must agree exactly with the array it is a shortcut for.
    import numpy as np

    from postcode_privacy.graph.adjacency import Adjacency
    from postcode_privacy.mechanism.hop import distribution

    n = 12
    edges = np.array([[i, i + 1] for i in range(n - 1)], dtype=np.int64)
    prior = np.arange(1, n + 1, dtype=np.int64)
    dist = distribution(
        Adjacency.from_edges(edges, n_nodes=n),
        prior,
        source=4,
        epsilon=1.0,
        radius=3,
    )

    full = dist.as_array(n)
    for node in range(n):
        assert dist.probability_of(node) == pytest.approx(full[node])


@pytest.mark.parametrize("seed", range(10))
def test_shell_node_arrays_are_sorted(seed: int) -> None:
    # probability_of and contains both binary-search these, so sortedness is a
    # load-bearing property of the BFS rather than a happy accident.
    import numpy as np

    from postcode_privacy.graph.adjacency import Adjacency
    from postcode_privacy.mechanism.hop import distribution

    rng = np.random.default_rng(seed)
    n = int(rng.integers(8, 40))
    edges = np.array([[i, i + 1] for i in range(n - 1)], dtype=np.int64)
    extra = rng.integers(0, n, size=(10, 2))
    edges = np.vstack([edges, extra[extra[:, 0] != extra[:, 1]]])

    dist = distribution(
        Adjacency.from_edges(edges, n_nodes=n),
        np.ones(n, dtype=np.int64),
        source=int(rng.integers(0, n)),
        epsilon=1.0,
        radius=3,
    )

    for shell in dist.shell_nodes:
        assert np.all(np.diff(shell) > 0)


@pytest.mark.parametrize(("radius", "epsilon"), [(2, 0.5), (4, 0.8), (6, 2.0)])
def test_the_closed_form_published_in_the_methods_note_matches_the_code(
    radius: int, epsilon: float
) -> None:
    # docs/methods.md states the normaliser as
    #     Z = sum_{h<R} q^h pi(S_h)  +  q^R (Pi - pi(B_R))
    # and the teleport probability as the second term over Z. A methods note
    # that drifts from its implementation is worse than none, so the published
    # formula is evaluated here independently and required to agree.
    import math

    import numpy as np

    from postcode_privacy.graph.adjacency import Adjacency
    from postcode_privacy.mechanism.hop import distribution

    n, source = 14, 6
    edges = np.array([[i, i + 1] for i in range(n - 1)], dtype=np.int64)
    prior = np.arange(1, n + 1, dtype=np.int64)
    dist = distribution(
        Adjacency.from_edges(edges, n_nodes=n),
        prior,
        source=source,
        epsilon=epsilon,
        radius=radius,
    )

    q = math.exp(-epsilon / 2)
    hops = np.abs(np.arange(n) - source)
    inside = hops < radius
    outside_mass = q**radius * (int(prior.sum()) - int(prior[inside].sum()))
    normaliser = (
        sum(q**h * int(prior[hops == h].sum()) for h in range(radius)) + outside_mass
    )

    assert dist.teleport_probability == pytest.approx(
        outside_mass / normaliser, rel=1e-12
    )
    # Shells zero to R-1 are enumerated; everything else sits at the floor.
    assert len(dist.shell_nodes) <= radius
    assert len(dist.ball) == int(inside.sum())
