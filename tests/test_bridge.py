"""Reconnecting components severed by pruning.

A postcode in a small disconnected component would be hidden only among that
component's members, and the component itself would be released exactly. Bridging
puts every node back inside one graph, so a sea crossing simply costs a hop.
"""

import numpy as np
import pytest
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from postcode_privacy.graph.bridge import bridge_components
from postcode_privacy.graph.build import delaunay_edges
from postcode_privacy.graph.prune import edge_lengths, prune_long_edges


def two_clusters() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    left = rng.uniform(0, 100, size=(12, 2))
    right = rng.uniform(0, 100, size=(12, 2)) + np.array([5000.0, 0.0])
    points = np.vstack([left, right])
    return points[:, 0], points[:, 1]


def test_bridging_reconnects_severed_components_with_one_shortest_edge() -> None:
    eastings, northings = two_clusters()
    edges = delaunay_edges(eastings, northings)
    kept, pruned = prune_long_edges(edges, eastings, northings, alpha=3.0)

    bridged, bridges = bridge_components(kept, pruned, eastings, northings, n_nodes=24)

    # Two components need exactly one bridge, and it should be the shortest of
    # the candidates rather than an arbitrary one.
    assert len(bridges) == 1
    assert edge_lengths(bridges, eastings, northings)[0] == pytest.approx(
        np.min(edge_lengths(pruned, eastings, northings))
    )
    assert len(bridged) == len(kept) + 1


def test_a_graph_that_is_already_connected_gains_no_bridges() -> None:
    rng = np.random.default_rng(2)
    points = rng.uniform(0, 100, size=(30, 2))
    eastings, northings = points[:, 0], points[:, 1]
    edges = delaunay_edges(eastings, northings)
    kept, pruned = prune_long_edges(edges, eastings, northings, alpha=3.0)

    bridged, bridges = bridge_components(kept, pruned, eastings, northings, n_nodes=30)

    assert len(bridges) == 0
    assert len(bridged) == len(kept)


@pytest.mark.parametrize("seed", range(25))
def test_the_graph_is_always_connected_after_bridging(seed: int) -> None:
    # The invariant the mechanism depends on. Clusters are placed at random
    # separations so that some runs sever the graph badly and others not at all.
    rng = np.random.default_rng(seed)
    n_clusters = rng.integers(1, 5)
    points = np.vstack(
        [
            rng.uniform(0, 100, size=(rng.integers(5, 20), 2))
            + rng.uniform(0, 20_000, size=2)
            for _ in range(n_clusters)
        ]
    )
    eastings, northings = points[:, 0], points[:, 1]
    n_nodes = len(points)

    edges = delaunay_edges(eastings, northings)
    kept, pruned = prune_long_edges(edges, eastings, northings, alpha=3.0)
    bridged, _ = bridge_components(kept, pruned, eastings, northings, n_nodes=n_nodes)

    adjacency = coo_matrix(
        (np.ones(len(bridged)), (bridged[:, 0], bridged[:, 1])),
        shape=(n_nodes, n_nodes),
    )
    n_components, _ = connected_components(adjacency, directed=False)
    assert n_components == 1
