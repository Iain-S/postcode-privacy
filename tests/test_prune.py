"""Adaptive pruning of over-long Delaunay edges.

Delaunay triangulates the convex hull, so it happily connects points across an
estuary or around a coastline. Those edges are lies about adjacency: the hop
metric would claim two postcodes are neighbours when nobody can get between
them. Pruning removes them.

The threshold is local rather than absolute. A five-kilometre cutoff is absurd
in central Manchester and far too aggressive in Caithness, so an edge is judged
against the typical edge length at its own endpoints.
"""

import numpy as np

from postcode_privacy.graph.build import delaunay_edges
from postcode_privacy.graph.prune import edge_lengths, prune_long_edges


def test_edges_spanning_a_gap_between_clusters_are_pruned() -> None:
    # Two tight clusters a long way apart: the only long edges are the ones
    # bridging the gap, which is the estuary case in miniature.
    rng = np.random.default_rng(0)
    left = rng.uniform(0, 100, size=(12, 2))
    right = rng.uniform(0, 100, size=(12, 2)) + np.array([5000.0, 0.0])
    points = np.vstack([left, right])
    eastings, northings = points[:, 0], points[:, 1]

    edges = delaunay_edges(eastings, northings)
    kept, pruned = prune_long_edges(edges, eastings, northings, alpha=3.0)

    def crosses_the_gap(edge: np.ndarray) -> bool:
        return (edge[0] < 12) != (edge[1] < 12)

    assert len(pruned) > 0
    assert all(crosses_the_gap(edge) for edge in pruned)
    assert not any(crosses_the_gap(edge) for edge in kept)


def test_pruning_never_touches_legitimate_local_edges() -> None:
    # The control that matters. A regular lattice does NOT survive pruning
    # untouched, and should not: Delaunay triangulates the convex hull, so a
    # lattice boundary grows sliver triangles joining distant near-collinear
    # points -- edges five and six units long in a unit grid. Those are the
    # coastline artefact in miniature and pruning them is the point. What must
    # never happen is losing a genuine nearest-neighbour edge.
    rng = np.random.default_rng(1)
    grid = np.array([(x, y) for x in range(8) for y in range(8)], dtype=float)
    grid += rng.uniform(-0.01, 0.01, size=grid.shape)
    eastings, northings = grid[:, 0], grid[:, 1]

    edges = delaunay_edges(eastings, northings)
    kept, pruned = prune_long_edges(edges, eastings, northings, alpha=3.0)

    lengths = edge_lengths(edges, eastings, northings)
    local = lengths < 1.5  # a lattice step is 1, a diagonal about 1.41
    assert local.sum() > 0

    kept_set = {tuple(edge) for edge in kept}
    assert all(tuple(edge) in kept_set for edge in edges[local])
    assert (edge_lengths(pruned, eastings, northings) > 3.0).all()
