"""Naive reference implementation, used as a test oracle.

Everything here is written to be obviously correct rather than fast: dense
matrices, full enumeration, no radius cap, no caching, floats throughout. The
optimised implementation is differentially tested against this module, so it
must stay simple enough that its correctness is self-evident on reading.

Library code must never import from here.
"""

import numpy as np
import numpy.typing as npt


def hop_distances(adjacency: npt.NDArray[np.bool_]) -> npt.NDArray[np.float64]:
    """All-pairs shortest-path hop distance, by Floyd-Warshall.

    Unreachable pairs are ``inf``.
    """
    n = adjacency.shape[0]
    distances = np.where(adjacency, 1.0, np.inf)
    np.fill_diagonal(distances, 0.0)

    for k in range(n):
        for i in range(n):
            for j in range(n):
                through_k = distances[i, k] + distances[k, j]
                if through_k < distances[i, j]:
                    distances[i, j] = through_k

    return distances


def distribution(
    adjacency: npt.NDArray[np.bool_],
    prior: npt.NDArray[np.float64],
    *,
    epsilon: float,
    radius: int,
    source: int,
) -> npt.NDArray[np.float64]:
    """The mechanism's exact output distribution for ``source``.

    ``P(y) proportional to prior[y] * exp(-epsilon * min(d(source, y), radius) / 2)``,
    computed by enumerating every node. The metric is capped at ``radius`` rather
    than the support being truncated, so every node keeps non-zero probability.
    """
    capped = np.minimum(hop_distances(adjacency)[source], radius)
    weights = prior * np.exp(-epsilon * capped / 2)
    return weights / weights.sum()
