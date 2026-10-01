"""Building the postcode adjacency graph from grid references."""

import numpy as np
import pytest
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from postcode_privacy.graph.build import delaunay_edges


def test_three_points_give_one_triangle_of_edges() -> None:
    eastings = np.array([0, 10, 0])
    northings = np.array([0, 0, 10])

    edges = delaunay_edges(eastings, northings)

    assert {tuple(edge) for edge in edges} == {(0, 1), (0, 2), (1, 2)}


@pytest.mark.parametrize("seed", range(15))
def test_an_unpruned_triangulation_is_always_connected(seed: int) -> None:
    # This is why pruning is off by default and bridging is not needed with it.
    # Delaunay triangulates the convex hull, so every point is reachable from
    # every other from the outset -- islands included. Bridging exists only to
    # repair what pruning severs; without pruning there is nothing to repair.
    rng = np.random.default_rng(seed)
    mainland = rng.uniform(0, 1000, size=(40, 2))
    island = rng.uniform(0, 20, size=(4, 2)) + np.array([9000.0, 9000.0])
    points = np.vstack([mainland, island])

    edges = delaunay_edges(points[:, 0], points[:, 1])

    adjacency = coo_matrix(
        (np.ones(len(edges)), (edges[:, 0], edges[:, 1])),
        shape=(len(points), len(points)),
    )
    n_components, _ = connected_components(adjacency, directed=False)
    assert n_components == 1
