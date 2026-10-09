"""The guarantee checked in exact arithmetic, with no floating-point slack.

`test_dp_guarantee.py` converts the mechanism's integer weights to float and
allows a relative tolerance of 1e-9. That is enough to confirm the mechanism is
applied in the right place, and far too coarse to see a violation caused by
rounding the exponential factors, which is of the order of 1e-17. The weights
are exact integers, so the ratio between any two of them is an exact rational
and nothing here needs a tolerance at all.

The one quantity that cannot be rational is `exp(epsilon * h)`, so it is
bounded *below* by a 60-digit decimal nudged down. Comparing against a lower
bound on the true bound is the conservative direction: anything this test
passes satisfies the real inequality too.
"""

from decimal import Decimal, localcontext
from fractions import Fraction

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from postcode_privacy._reference import hop_distances
from postcode_privacy.graph.adjacency import Adjacency
from postcode_privacy.mechanism.hop import (
    Distribution,
    _powers,
    distribution,
    q_upper_bound,
)


def exp_lower_bound(exponent: int, epsilon: float) -> Fraction:
    """A rational that is provably no greater than ``exp(epsilon * exponent)``."""
    if exponent == 0:
        return Fraction(1)
    with localcontext() as ctx:
        ctx.prec = 1200
        product = Decimal(epsilon) * exponent
        ctx.prec = 60
        value = +product
        value = value.exp()
    # `Decimal.exp` is correctly rounded, so the result is within half an ulp of
    # the truth; the division by (1 + 1e-50) covers that with room to spare.
    return Fraction(value) / (1 + Fraction(1, 10**50))


def exact_weight(dist: Distribution, node: int) -> int:
    """``prior(node) * q**capped_distance``, as the exact integer the sampler uses."""
    for hop, nodes in enumerate(dist.shell_nodes):
        if node in set(nodes.tolist()):
            return int(dist.prior[node]) * dist.powers[hop]
    return int(dist.prior[node]) * dist.powers[dist.radius]


def worst_excess(
    adjacency: npt.NDArray[np.bool_],
    prior: npt.NDArray[np.int64],
    *,
    epsilon: float,
    radius: int,
) -> Fraction:
    """How far the worst triple exceeds its bound. Non-positive means compliant."""
    n = adjacency.shape[0]
    edges = np.argwhere(np.triu(adjacency, k=1)).astype(np.int64)
    graph = Adjacency.from_edges(edges.reshape(-1, 2), n_nodes=n)
    capped = np.minimum(hop_distances(adjacency), radius)

    dists = [
        distribution(graph, prior, source=x, epsilon=epsilon, radius=radius)
        for x in range(n)
    ]
    totals = [Fraction(d.total_weight) for d in dists]

    excess = Fraction(-1)
    for x in range(n):
        for other in range(n):
            bound = exp_lower_bound(int(capped[x, other]), epsilon)
            for y in range(n):
                ratio = (
                    Fraction(exact_weight(dists[x], y), exact_weight(dists[other], y))
                    * totals[other]
                    / totals[x]
                )
                excess = max(excess, ratio - bound)
    return excess


def test_the_prior_that_exposed_the_rounding() -> None:
    """The counterexample from issue #6, checked exactly rather than in float.

    A two-node graph with a prior spanning the full int64 range: the smaller
    node's weight is one unit of quantisation, so the rounding of `q` shows up
    undiluted in the ratio. Before the conservative power construction this
    exceeded `exp(0.3)` by about 1.25e-17.
    """
    adjacency = np.array([[False, True], [True, False]])
    prior = np.array([1, 2**62 - 1], dtype=np.int64)
    assert worst_excess(adjacency, prior, epsilon=0.3, radius=1) <= 0


@given(
    epsilon=st.floats(min_value=0.01, max_value=5.0),
    radius=st.integers(min_value=1, max_value=6),
    exponent=st.integers(min_value=0, max_value=60),
)
@settings(max_examples=50, deadline=None)
def test_extreme_priors_do_not_break_the_bound(
    epsilon: float, radius: int, exponent: int
) -> None:
    """One node carrying almost all the prior mass, the rest carrying one each.

    A prior that is nearly a point mass maximises the influence of the smallest
    representable weight, which is where quantisation error is largest relative
    to the weight it perturbs.
    """
    adjacency = np.array(
        [
            [False, True, False, False],
            [True, False, True, False],
            [False, True, False, True],
            [False, False, True, False],
        ]
    )
    prior = np.array([1, 1, 1, 2**exponent], dtype=np.int64)
    assert worst_excess(adjacency, prior, epsilon=epsilon, radius=radius) <= 0


@given(
    epsilon=st.floats(min_value=0.05, max_value=4.0),
    radius=st.integers(min_value=1, max_value=5),
    prior_seed=st.integers(min_value=0, max_value=2**32 - 1),
    n=st.integers(min_value=2, max_value=5),
    upper=st.data(),
)
@settings(max_examples=120, deadline=None)
def test_the_guarantee_holds_exactly_on_small_graphs(
    epsilon: float,
    radius: int,
    prior_seed: int,
    n: int,
    upper: st.DataObject,
) -> None:
    bits = upper.draw(
        st.lists(st.booleans(), min_size=n * (n - 1) // 2, max_size=n * (n - 1) // 2)
    )
    adjacency = np.zeros((n, n), dtype=bool)
    adjacency[np.triu_indices(n, k=1)] = bits
    adjacency |= adjacency.T

    rng = np.random.default_rng(prior_seed)
    prior = rng.integers(1, 10**6, size=n, dtype=np.int64)
    assert worst_excess(adjacency, prior, epsilon=epsilon, radius=radius) <= 0


def test_a_prior_too_large_to_sample_is_refused() -> None:
    """The supported bound on total prior mass is stated and enforced.

    Weights are unbounded Python integers, but the sampler accumulates the prior
    itself in int64, so the total is what has to fit. Refusing is better than
    overflowing a cumulative sum and drawing from a silently wrong distribution.
    """
    edges = np.array([[0, 1]], dtype=np.int64)
    graph = Adjacency.from_edges(edges, n_nodes=2)
    prior = np.array([2**62, 2**62], dtype=np.int64)
    with pytest.raises(ValueError, match="total prior"):
        distribution(graph, prior, source=0, epsilon=1.0, radius=2)


@given(
    epsilon=st.floats(min_value=0.01, max_value=5.0),
    radius=st.integers(min_value=1, max_value=70),
)
@settings(max_examples=200, deadline=None)
def test_the_powers_decay_no_faster_than_q(epsilon: float, radius: int) -> None:
    """The inequality the proof actually rests on, checked directly.

    The end-to-end triple enumeration above is the statement users care about,
    but on any particular graph it has slack: the ratio usually sits well below
    its bound, so a sub-unit error in a single power need not surface. This is
    the sharp version -- `P[j + h] >= q**h * P[j]` for every pair -- and it is
    what makes the guarantee hold on *every* graph and prior rather than the
    ones a test happened to generate.

    `q**h` is bounded below rationally, so the comparison is exact.
    """
    q = q_upper_bound(epsilon)
    powers = _powers(scale=128, radius=radius, q=q)

    with localcontext() as ctx:
        ctx.prec = 1200
        half = Decimal(-epsilon) * Decimal("0.5")

    for step in range(1, radius + 1):
        with localcontext() as ctx:
            ctx.prec = 80
            factor = Fraction((+(half * step)).exp()) * (1 + Fraction(1, 10**60))
        for start in range(radius + 1 - step):
            assert powers[start + step] >= factor * powers[start], (
                f"powers decay faster than q at step {start} -> {start + step}: "
                f"the likelihood ratio can then exceed exp({epsilon} * {step})"
            )
