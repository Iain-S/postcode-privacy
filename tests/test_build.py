"""Building the postcode adjacency graph from grid references."""

import numpy as np

from postcode_privacy.graph.build import delaunay_edges


def test_three_points_give_one_triangle_of_edges() -> None:
    eastings = np.array([0, 10, 0])
    northings = np.array([0, 0, 10])

    edges = delaunay_edges(eastings, northings)

    assert {tuple(edge) for edge in edges} == {(0, 1), (0, 2), (1, 2)}
