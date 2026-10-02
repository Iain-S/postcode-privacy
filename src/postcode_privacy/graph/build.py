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
import numpy.typing as npt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import Delaunay

from postcode_privacy._types import Coordinates, Edges
from postcode_privacy.graph.bridge import bridge_components
from postcode_privacy.graph.prune import edge_lengths, prune_long_edges


def delaunay_edges(eastings: Coordinates, northings: Coordinates) -> Edges:
    """Undirected edges of the Delaunay triangulation of the given points.

    Coordinates are OSGB36 eastings and northings in metres. They are projected,
    so Euclidean distance between them is honest and the triangulation needs no
    spherical correction.

    Points sharing a coordinate need care. Qhull discards duplicates, so a naive
    triangulation leaves every duplicated postcode in no simplex at all --
    isolated, infinitely far from the rest of the country. Under the capped
    metric such a node's mechanism returns its own true postcode with
    probability very close to one, so the privacy loss is total and silent. Real
    ONSPD data has tens of thousands of them. Here the triangulation is computed
    over distinct coordinates and then expanded, so that postcodes at the same
    point are adjacent to each other and share the same outside neighbours --
    one place, fully interchangeable members.

    Returns an ``(m, 2)`` array of node index pairs, each with the lower index
    first, sorted and deduplicated so the output does not depend on the order
    Qhull happened to emit simplices in.
    """
    points = np.column_stack([eastings, northings]).astype(np.float64)
    locations, node_location = np.unique(points, axis=0, return_inverse=True)
    node_location = node_location.ravel()

    simplices = Delaunay(locations).simplices
    pairs = np.concatenate(
        [simplices[:, [0, 1]], simplices[:, [1, 2]], simplices[:, [0, 2]]]
    )
    location_edges = np.unique(np.sort(pairs, axis=1), axis=0)

    if len(locations) == len(points):
        return location_edges.astype(np.int64)

    return _expand_to_nodes(location_edges, node_location, len(locations))


def _expand_to_nodes(
    location_edges: Edges, node_location: npt.NDArray[np.intp], n_locations: int
) -> Edges:
    """Lift edges between locations to edges between the nodes at them.

    Every node at location ``u`` is joined to every node at location ``v``, and
    the nodes sharing a location are joined to each other. The common case by far
    is one node per location, which is handled without any per-edge work.
    """
    order = np.argsort(node_location, kind="stable")
    starts = np.searchsorted(node_location[order], np.arange(n_locations + 1))
    members = [order[starts[i] : starts[i + 1]] for i in range(n_locations)]
    sizes = np.diff(starts)

    simple = (sizes[location_edges[:, 0]] == 1) & (sizes[location_edges[:, 1]] == 1)
    edges = [
        np.column_stack(
            [
                order[starts[location_edges[simple, 0]]],
                order[starts[location_edges[simple, 1]]],
            ]
        )
    ]

    for u, v in location_edges[~simple]:
        left, right = members[u], members[v]
        edges.append(
            np.column_stack([np.repeat(left, len(right)), np.tile(right, len(left))])
        )

    for group in (m for m, size in zip(members, sizes, strict=True) if size > 1):
        a, b = np.triu_indices(len(group), k=1)
        edges.append(np.column_stack([group[a], group[b]]))

    stacked = np.sort(np.concatenate(edges), axis=1)
    return np.unique(stacked, axis=0).astype(np.int64)


class GraphIntegrityError(ValueError):
    """Raised when a graph would give some nodes no meaningful privacy."""


def check_integrity(edges: Edges, *, n_nodes: int) -> None:
    """Fail if any node is isolated or the graph is disconnected.

    This asserts the *consequence* rather than any particular cause. A node cut
    off from the rest of the graph is infinitely far from every other postcode,
    so under the capped metric its output distribution collapses onto its own
    true value: the mechanism hands back the secret, without erroring, warning,
    or looking unusual.

    One cause of that was found in real data -- Qhull discards duplicate points,
    stranding 57,030 postcodes that shared a centroid. The next cause will be
    something else, which is why this check is phrased in terms of what must be
    true rather than what has previously gone wrong.
    """
    degree = np.bincount(edges.ravel(), minlength=n_nodes)
    isolated = int((degree == 0).sum())
    if isolated:
        raise GraphIntegrityError(
            f"{isolated:,} of {n_nodes:,} nodes are isolated and would receive no "
            "privacy: their output distribution collapses onto their own true value."
        )

    adjacency = coo_matrix(
        (np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n_nodes, n_nodes)
    )
    n_components, labels = connected_components(adjacency, directed=False)
    if n_components > 1:
        smallest = int(np.min(np.bincount(labels)))
        raise GraphIntegrityError(
            f"graph has {n_components:,} connected components; the smallest holds "
            f"{smallest:,} node(s). Nodes cannot be hidden outside their own "
            "component, so a small component means little or no privacy."
        )


# No two UK postcodes fifty kilometres apart are neighbours under any reading
# of the word. This is an absolute claim about what adjacency can mean, not a
# density judgement like `prune_alpha`, which is why it can be a default when
# that one cannot. Measured on the August 2026 build, it removes 264 edges of
# 5.36 million, fragments nothing, and cuts the displacement tail for the
# affected postcodes from a p95 of 487 km to 72 km.
DEFAULT_MAX_EDGE_KM = 50.0
METRES_PER_KM = 1000.0


@dataclass(frozen=True)
class AssembledGraph:
    """The edge set of a postcode graph, and a record of how it was altered."""

    edges: Edges
    cut: Edges
    pruned: Edges
    bridges: Edges


def _reconnect(
    kept: Edges,
    candidates: Edges,
    eastings: Coordinates,
    northings: Coordinates,
    *,
    n_nodes: int,
) -> Edges:
    """Put back the fewest, shortest cut edges needed to keep one component."""
    if not len(candidates):
        return kept
    bridged, _ = bridge_components(
        kept, candidates, eastings, northings, n_nodes=n_nodes
    )
    return bridged


def assemble(
    eastings: Coordinates,
    northings: Coordinates,
    *,
    max_edge_km: float | None = DEFAULT_MAX_EDGE_KM,
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
    n_nodes = len(np.asarray(eastings))
    edges = delaunay_edges(eastings, northings)
    empty = np.empty((0, 2), dtype=np.int64)
    cut = empty

    if max_edge_km is not None:
        lengths = edge_lengths(edges, eastings, northings)
        too_far = lengths > max_edge_km * METRES_PER_KM
        edges, cut = edges[~too_far], edges[too_far]
        # On the real national graph this fragments nothing at fifty
        # kilometres, but a synthetic graph can, and a disconnected graph is
        # where the mechanism hands a subject their own postcode back.
        edges = _reconnect(edges, cut, eastings, northings, n_nodes=n_nodes)

    if prune_alpha is None:
        check_integrity(edges, n_nodes=n_nodes)
        return AssembledGraph(edges=edges, cut=cut, pruned=empty, bridges=empty)

    kept, pruned = prune_long_edges(edges, eastings, northings, alpha=prune_alpha)
    bridged, bridges = bridge_components(
        kept, pruned, eastings, northings, n_nodes=n_nodes
    )
    check_integrity(bridged, n_nodes=n_nodes)
    return AssembledGraph(edges=bridged, cut=cut, pruned=pruned, bridges=bridges)
