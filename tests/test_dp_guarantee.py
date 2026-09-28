"""The differential privacy guarantee, checked exhaustively.

On graphs small enough to enumerate, we do not estimate the guarantee from
samples -- we check every (x, x', y) triple. For a given graph that is a proof,
not evidence.
"""

import numpy as np
import numpy.typing as npt
from hypothesis import given, settings
from hypothesis import strategies as st

from postcode_privacy._reference import distribution, hop_distances

# Floating point slack. The guarantee is exact; only the arithmetic is not.
TOLERANCE = 1 + 1e-9


@st.composite
def graphs(draw: st.DrawFn, max_nodes: int = 7) -> npt.NDArray[np.bool_]:
    """An undirected graph with no self-loops, possibly disconnected.

    Disconnected graphs are deliberately included: the capped metric must keep
    the guarantee intact across components, which is precisely what lets the
    graph builder bridge islands without special-casing the mechanism.
    """
    n = draw(st.integers(min_value=2, max_value=max_nodes))
    upper = draw(
        st.lists(st.booleans(), min_size=n * (n - 1) // 2, max_size=n * (n - 1) // 2)
    )
    adjacency = np.zeros((n, n), dtype=bool)
    adjacency[np.triu_indices(n, k=1)] = upper
    return adjacency | adjacency.T


@given(
    adjacency=graphs(),
    epsilon=st.floats(min_value=0.01, max_value=5.0),
    radius=st.integers(min_value=1, max_value=8),
)
@settings(max_examples=300, deadline=None)
def test_likelihood_ratio_is_bounded_by_exp_epsilon_times_hop_distance(
    adjacency: npt.NDArray[np.bool_], epsilon: float, radius: int
) -> None:
    n = adjacency.shape[0]
    prior = np.ones(n)
    capped = np.minimum(hop_distances(adjacency), radius)
    distributions = [
        distribution(adjacency, prior, epsilon=epsilon, radius=radius, source=x)
        for x in range(n)
    ]

    for x in range(n):
        for other in range(n):
            bound = np.exp(epsilon * capped[x, other]) * TOLERANCE
            for y in range(n):
                ratio = distributions[x][y] / distributions[other][y]
                assert ratio <= bound, (
                    f"epsilon*d-privacy violated: P({y}|{x})/P({y}|{other}) = "
                    f"{ratio} exceeds exp({epsilon} * {capped[x, other]}) = {bound}"
                )
