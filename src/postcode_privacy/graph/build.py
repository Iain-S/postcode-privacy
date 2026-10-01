"""Turning postcode grid references into an adjacency graph.

Delaunay triangulation is the natural "who is my neighbour" relation for
irregularly spaced points: it is planar, and its mean degree is about six
regardless of local density. That density independence is the property the whole
design rests on -- one hop means roughly the same thing in a city as in a glen,
even though it means wildly different numbers of metres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import Delaunay

from postcode_privacy._types import Coordinates, Edges
from postcode_privacy.graph.bridge import bridge_components
from postcode_privacy.graph.prune import prune_long_edges


def delaunay_edges(eastings: Coordinates, northings: Coordinates) -> Edges:
    """Undirected edges of the Delaunay triangulation of the given points.

    Coordinates are OSGB36 eastings and northings in metres. They are projected,
    so Euclidean distance between them is honest and the triangulation needs no
    spherical correction.

    Returns an ``(m, 2)`` array of node index pairs, each with the lower index
    first, sorted and deduplicated so the output does not depend on the order
    Qhull happened to emit simplices in.
    """
    points = np.column_stack([eastings, northings]).astype(np.float64)
    simplices = Delaunay(points).simplices

    pairs = np.concatenate(
        [simplices[:, [0, 1]], simplices[:, [1, 2]], simplices[:, [0, 2]]]
    )
    pairs = np.sort(pairs, axis=1)
    return np.unique(pairs, axis=0).astype(np.int64)


@dataclass(frozen=True)
class AssembledGraph:
    """The edge set of a postcode graph, and a record of how it was altered."""

    edges: Edges
    pruned: Edges
    bridges: Edges


def assemble(
    eastings: Coordinates,
    northings: Coordinates,
    *,
    prune_alpha: float | None = None,
) -> AssembledGraph:
    """Build the postcode graph from grid references.

    By default the triangulation is used unmodified. Pruning is opt-in because
    its threshold is a guess: no geometric criterion can distinguish an estuary
    from an empty moor, since in a point set they are the same thing -- a gap
    with nothing in it. Parameter-free alternatives such as the Gabriel and
    relative-neighbourhood graphs keep those edges for the same reason. Doing it
    properly needs road or hydrography data, which v1 does not take on.

    Leaving pruning off also removes the need to bridge. Delaunay triangulates
    the convex hull, so the unmodified graph already connects every point,
    islands included; bridging exists only to repair what pruning severs.

    Setting ``prune_alpha`` enables both, so the cost of the artefacts can be
    measured against the cost of the heuristic.
    """
    edges = delaunay_edges(eastings, northings)
    empty = np.empty((0, 2), dtype=np.int64)

    if prune_alpha is None:
        return AssembledGraph(edges=edges, pruned=empty, bridges=empty)

    kept, pruned = prune_long_edges(edges, eastings, northings, alpha=prune_alpha)
    n_nodes = len(np.asarray(eastings))
    bridged, bridges = bridge_components(
        kept, pruned, eastings, northings, n_nodes=n_nodes
    )
    return AssembledGraph(edges=bridged, pruned=pruned, bridges=bridges)
