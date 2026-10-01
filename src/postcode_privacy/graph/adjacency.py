"""Compressed adjacency, and breadth-first expansion from a source."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from postcode_privacy._types import Edges


@dataclass(frozen=True)
class Adjacency:
    """An undirected graph in compressed sparse row form."""

    indptr: npt.NDArray[np.int64]
    indices: npt.NDArray[np.int64]

    @property
    def n_nodes(self) -> int:
        return len(self.indptr) - 1

    @classmethod
    def from_edges(cls, edges: Edges, *, n_nodes: int) -> Adjacency:
        """Build from an ``(m, 2)`` edge array, storing each edge both ways."""
        both = np.concatenate([edges, edges[:, ::-1]])
        order = np.argsort(both[:, 0], kind="stable")
        sources, targets = both[order, 0], both[order, 1]
        counts = np.bincount(sources, minlength=n_nodes)
        indptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        return cls(indptr=indptr, indices=targets.astype(np.int64))

    def neighbours(self, node: int) -> npt.NDArray[np.int64]:
        return self.indices[self.indptr[node] : self.indptr[node + 1]]

    def ball(
        self, *, source: int, radius: int
    ) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
        """Nodes within ``radius`` hops of ``source``, with their hop distances.

        Expansion is shell by shell rather than node by node, because the
        mechanism's weight depends only on which shell a node falls in. Each node
        appears once, at its shortest distance.
        """
        seen = np.zeros(self.n_nodes, dtype=bool)
        seen[source] = True
        frontier = np.array([source], dtype=np.int64)

        nodes = [frontier]
        hops = [np.zeros(1, dtype=np.int64)]

        for hop in range(1, radius + 1):
            if not len(frontier):
                break
            candidates = np.concatenate(
                [self.neighbours(int(node)) for node in frontier]
            )
            candidates = np.unique(candidates)
            frontier = candidates[~seen[candidates]]
            if not len(frontier):
                break
            seen[frontier] = True
            nodes.append(frontier)
            hops.append(np.full(len(frontier), hop, dtype=np.int64))

        return np.concatenate(nodes), np.concatenate(hops)
