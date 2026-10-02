"""Assembling the graph end to end.

Pruning is off by default. It relies on a geometric threshold that cannot
distinguish an estuary from an empty moor -- the information is simply not in a
point set -- so v1 ships the unmodified triangulation and measures what the
artefacts cost rather than guessing at a parameter.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from postcode_privacy.graph.build import assemble, delaunay_edges
from postcode_privacy.graph.prune import edge_lengths


def two_clusters() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    left = rng.uniform(0, 100, size=(12, 2))
    right = rng.uniform(0, 100, size=(12, 2)) + np.array([5000.0, 0.0])
    points = np.vstack([left, right])
    return points[:, 0], points[:, 1]


def test_by_default_the_triangulation_is_used_unmodified() -> None:
    eastings, northings = two_clusters()

    graph = assemble(eastings, northings)

    assert len(graph.edges) == len(delaunay_edges(eastings, northings))
    assert len(graph.pruned) == 0
    assert len(graph.bridges) == 0


def test_pruning_is_available_and_reports_what_it_changed() -> None:
    eastings, northings = two_clusters()

    graph = assemble(eastings, northings, prune_alpha=3.0)

    assert len(graph.pruned) > 0
    # Pruning severs the two clusters, so bridging must put them back.
    assert len(graph.bridges) == 1
    assert len(graph.edges) < len(delaunay_edges(eastings, northings))


def test_absurdly_long_edges_are_cut_by_default() -> None:
    # Delaunay tiles the convex hull, so it triangulates across concavities:
    # on real data it produced edges of 920 km, Great Yarmouth to Shetland
    # straight over the North Sea. Those are not adjacency under any reading.
    far = 200_000.0  # metres
    eastings = np.array([0.0, 1000.0, 2000.0, far, far + 1000.0, far + 2000.0])
    northings = np.array([0.0, 500.0, 0.0, 0.0, 500.0, 0.0])

    graph = assemble(eastings, northings, max_edge_km=50.0)

    assert len(graph.cut) > 0
    lengths = edge_lengths(graph.cut, eastings, northings)
    assert np.min(lengths) > 50_000


def test_cutting_long_edges_never_leaves_the_graph_disconnected() -> None:
    # The invariant the mechanism depends on. On the real national graph a
    # 50 km cut fragments nothing, but a synthetic one can, and a disconnected
    # graph is where the mechanism hands back the secret.
    far = 200_000.0
    eastings = np.array([0.0, 1000.0, 2000.0, far, far + 1000.0, far + 2000.0])
    northings = np.array([0.0, 500.0, 0.0, 0.0, 500.0, 0.0])

    graph = assemble(eastings, northings, max_edge_km=50.0)

    adjacency = coo_matrix(
        (np.ones(len(graph.edges)), (graph.edges[:, 0], graph.edges[:, 1])),
        shape=(6, 6),
    )
    assert connected_components(adjacency, directed=False)[0] == 1


def test_the_cut_can_be_turned_off() -> None:
    far = 200_000.0
    eastings = np.array([0.0, 1000.0, 2000.0, far, far + 1000.0, far + 2000.0])
    northings = np.array([0.0, 500.0, 0.0, 0.0, 500.0, 0.0])

    graph = assemble(eastings, northings, max_edge_km=None)

    assert len(graph.cut) == 0
    assert len(graph.edges) == len(delaunay_edges(eastings, northings))


def test_a_normal_graph_loses_nothing_to_the_cut() -> None:
    # 50 km is an absolute claim about what adjacency can mean in the UK, not a
    # density judgement, so it must never touch an ordinary neighbourhood.
    rng = np.random.default_rng(5)
    points = rng.uniform(0, 20_000, size=(60, 2))

    graph = assemble(points[:, 0], points[:, 1])

    assert len(graph.cut) == 0
