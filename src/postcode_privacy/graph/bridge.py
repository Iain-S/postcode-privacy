"""Reconnecting the components that pruning severs.

A node in a small isolated component is hidden only among that component's
members, and the component's identity is released exactly -- a resident of the
Isles of Scilly would get almost no protection. Bridging restores a single
connected graph so that crossing water simply costs a hop, and the mechanism
needs no special case for islands.

The candidate bridges are the pruned edges themselves. Before pruning, the
Delaunay triangulation spans every point, so the edges pruning removed are
guaranteed to be sufficient to put the graph back together -- and each one is a
Delaunay edge, so a bridge always joins genuinely facing points rather than an
arbitrary pair.
"""

from __future__ import annotations

import numpy as np

from postcode_privacy._types import Coordinates, Edges
from postcode_privacy.graph.prune import edge_lengths


class _DisjointSet:
    """Union-find over node indices."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, node: int) -> int:
        while self._parent[node] != node:
            self._parent[node] = self._parent[self._parent[node]]
            node = self._parent[node]
        return node

    def union(self, a: int, b: int) -> bool:
        """Merge the sets containing ``a`` and ``b``; False if already merged."""
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return False
        self._parent[root_b] = root_a
        return True


def bridge_components(
    kept: Edges,
    pruned: Edges,
    eastings: Coordinates,
    northings: Coordinates,
    *,
    n_nodes: int,
) -> tuple[Edges, Edges]:
    """Add the fewest, shortest pruned edges needed to reconnect the graph.

    This is Kruskal's algorithm over the pruned edges: shortest first, keeping
    only those that join two components that are still separate. The result is a
    minimum spanning forest of the components, so the graph is reconnected as
    cheaply as the geometry allows.

    Returns the full edge set including bridges, and the bridges alone.
    """
    components = _DisjointSet(n_nodes)
    for a, b in kept:
        components.union(int(a), int(b))

    bridges: list[tuple[int, int]] = []
    order = np.argsort(edge_lengths(pruned, eastings, northings), kind="stable")
    for a, b in pruned[order]:
        if components.union(int(a), int(b)):
            bridges.append((int(a), int(b)))

    bridge_array = np.array(bridges, dtype=np.int64).reshape(-1, 2)
    return np.vstack([kept, bridge_array]).astype(np.int64), bridge_array
