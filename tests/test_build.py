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


def duplicated_points() -> tuple[np.ndarray, np.ndarray]:
    """A small grid where three nodes share one coordinate."""
    rng = np.random.default_rng(3)
    base = rng.uniform(0, 100, size=(12, 2))
    shared = np.repeat(base[[0]], 3, axis=0)
    points = np.vstack([base, shared])
    return points[:, 0], points[:, 1]


def test_postcodes_sharing_a_coordinate_are_not_isolated() -> None:
    # Real ONSPD data has 57,030 postcodes sharing a centroid with another, the
    # largest group being 1,161 at one point. Qhull discards duplicate points, so
    # a naive triangulation leaves every one of them in no simplex at all --
    # degree zero, infinitely far from everything. The capped metric then makes
    # the mechanism return their true postcode with probability ~1, which is a
    # total and silent loss of privacy for 3% of the country.
    eastings, northings = duplicated_points()

    edges = delaunay_edges(eastings, northings)

    referenced = np.unique(edges)
    assert len(referenced) == len(eastings), "every node must have at least one edge"


def test_co_located_postcodes_are_adjacent_and_interchangeable() -> None:
    # Sharing a centroid means being the same place, so co-located postcodes are
    # one hop apart and have identical neighbours. Without the second property
    # they would not be substitutable for one another, which is precisely what
    # the mechanism needs them to be.
    eastings, northings = duplicated_points()
    group = [0, 12, 13, 14]  # node 0 and the three copies of its coordinate

    edges = delaunay_edges(eastings, northings)

    neighbours = {node: set() for node in range(len(eastings))}
    for a, b in edges:
        neighbours[int(a)].add(int(b))
        neighbours[int(b)].add(int(a))

    for node in group:
        assert set(group) - {node} <= neighbours[node], "co-located must be adjacent"

    outside = [set(neighbours[n]) - set(group) for n in group]
    assert all(o == outside[0] for o in outside), "co-located must share neighbours"
