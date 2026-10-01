"""Drawing an output from the distribution.

The sampler is a pure function of one integer from the PRF, so almost all of it
is tested by enumeration rather than by sampling.
"""

import numpy as np
import pytest

from postcode_privacy.graph.adjacency import Adjacency
from postcode_privacy.mechanism.hop import distribution
from postcode_privacy.mechanism.prf import Key
from postcode_privacy.mechanism.sample import choose, sample

PATH_EDGES = np.array([[0, 1], [1, 2], [2, 3]], dtype=np.int64)


def test_choose_lands_in_the_first_bucket_at_the_bottom_of_its_range() -> None:
    cumulative = [3, 5, 9]  # buckets of width 3, 2, 4

    assert choose(cumulative, 0) == 0
    assert choose(cumulative, 2) == 0


def test_choose_switches_bucket_exactly_at_the_boundary() -> None:
    # Off-by-one here would skew every draw towards one neighbour.
    cumulative = [3, 5, 9]

    assert choose(cumulative, 2) == 0
    assert choose(cumulative, 3) == 1
    assert choose(cumulative, 4) == 1
    assert choose(cumulative, 5) == 2


def test_choose_covers_the_whole_range_exhaustively() -> None:
    # Every draw in [0, total) maps to exactly one bucket, and each bucket is
    # hit exactly as often as its width.
    cumulative = [3, 5, 9]

    counts = np.bincount([choose(cumulative, d) for d in range(9)], minlength=3)

    assert counts.tolist() == [3, 2, 4]


def test_a_zero_width_bucket_is_never_chosen() -> None:
    # An empty shell has zero weight and must never be selected.
    cumulative = [2, 2, 4]  # middle bucket has width 0

    assert {choose(cumulative, d) for d in range(4)} == {0, 2}


def test_sampling_is_deterministic_for_a_subject() -> None:
    graph = Adjacency.from_edges(PATH_EDGES, n_nodes=4)
    prior = np.array([3, 1, 4, 1], dtype=np.int64)
    dist = distribution(graph, prior, source=0, epsilon=1.0, radius=3)
    key = Key.from_bytes(b"\x01" * 32)

    first = sample(dist, key=key, fields=(b"patient-1", b"LS2 9JT"))
    second = sample(dist, key=key, fields=(b"patient-1", b"LS2 9JT"))

    assert first == second


def test_a_different_key_gives_a_different_mapping() -> None:
    graph = Adjacency.from_edges(PATH_EDGES, n_nodes=4)
    prior = np.array([1, 1, 1, 1], dtype=np.int64)
    dist = distribution(graph, prior, source=0, epsilon=0.1, radius=3)
    fields = (b"patient-1", b"LS2 9JT")

    outputs = {
        sample(dist, key=Key.from_bytes(bytes([n]) * 32), fields=fields)
        for n in range(1, 40)
    }

    assert len(outputs) > 1, "all keys produced the same output"


@pytest.mark.statistical
def test_sampling_realises_the_distribution() -> None:
    """End to end: do the draws actually follow the distribution?

    Every other test here enumerates. This one samples, because nothing else
    checks that the two stages compose into the intended whole. It is
    deterministic despite being statistical -- the subject identifiers are
    fixed and the PRF is keyed -- so it cannot flake. A flaky test in a privacy
    library teaches people to re-run failures.
    """
    graph = Adjacency.from_edges(PATH_EDGES, n_nodes=4)
    prior = np.array([3, 1, 4, 1], dtype=np.int64)
    dist = distribution(graph, prior, source=1, epsilon=0.8, radius=2)
    key = Key.from_bytes(b"\x07" * 32)

    draws = [
        sample(dist, key=key, fields=(f"subject-{i}".encode(),)) for i in range(20_000)
    ]
    empirical = np.bincount(draws, minlength=4) / len(draws)

    np.testing.assert_allclose(empirical, dist.as_array(4), atol=0.01)


def test_every_sample_is_a_real_node() -> None:
    graph = Adjacency.from_edges(PATH_EDGES, n_nodes=4)
    prior = np.array([3, 1, 4, 1], dtype=np.int64)
    dist = distribution(graph, prior, source=0, epsilon=2.0, radius=1)
    key = Key.from_bytes(b"\x05" * 32)

    for i in range(500):
        node = sample(dist, key=key, fields=(f"s{i}".encode(),))
        assert 0 <= node < 4


def test_the_tail_is_reachable_and_the_ball_is_not_over_sampled() -> None:
    # With a radius of 1 only the source itself is inside the ball, so every
    # other node must arrive through the tail's rejection sampling.
    graph = Adjacency.from_edges(PATH_EDGES, n_nodes=4)
    prior = np.array([1, 1, 1, 1], dtype=np.int64)
    dist = distribution(graph, prior, source=0, epsilon=0.01, radius=1)
    key = Key.from_bytes(b"\x09" * 32)

    seen = {sample(dist, key=key, fields=(f"s{i}".encode(),)) for i in range(400)}

    assert seen == {0, 1, 2, 3}, "tail sampling must be able to reach every node"


STAR_EDGES = np.array([[0, n] for n in range(1, 9)], dtype=np.int64)


@pytest.mark.statistical
def test_every_postcode_in_a_ring_is_reachable_and_equally_likely() -> None:
    """Within-shell draws must spread across the whole ring.

    A path graph cannot show this: its shells hold one node each, so the second
    stage is never exercised. A star's first shell holds eight nodes of equal
    prior, which must therefore come up equally often. This covers the second
    stage composing correctly -- a mis-sized bound or a truncated cumulative
    array would starve some of the ring.
    """
    graph = Adjacency.from_edges(STAR_EDGES, n_nodes=9)
    prior = np.ones(9, dtype=np.int64)
    dist = distribution(graph, prior, source=0, epsilon=1.0, radius=2)
    key = Key.from_bytes(b"\x0b" * 32)

    draws = [
        sample(dist, key=key, fields=(f"subject-{i}".encode(),)) for i in range(8_000)
    ]
    leaves = np.bincount(draws, minlength=9)[1:]

    assert (leaves > 0).all(), f"some leaves are unreachable: {leaves.tolist()}"
    # The eight leaves are symmetric, so none should dominate.
    assert int(np.max(leaves)) / int(np.min(leaves)) < 1.5, (
        f"uneven within-shell draw: {leaves.tolist()}"
    )
