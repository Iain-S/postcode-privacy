"""Removing Delaunay edges that assert adjacency across impassable ground."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.spatial import KDTree

from postcode_privacy._types import Coordinates, Edges

DEFAULT_ALPHA = 3.0

# Delaunay triangulations have a mean degree of about six, so six neighbours is
# the natural neighbourhood size for measuring how densely packed a node is.
LOCAL_SCALE_NEIGHBOURS = 6


def edge_lengths(
    edges: Edges,
    eastings: Coordinates,
    northings: Coordinates,
) -> npt.NDArray[np.float64]:
    """Euclidean length of each edge, in the units of the grid reference."""
    points = np.column_stack([eastings, northings]).astype(np.float64)
    return np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)


def local_scale(
    eastings: Coordinates,
    northings: Coordinates,
    *,
    neighbours: int = LOCAL_SCALE_NEIGHBOURS,
) -> npt.NDArray[np.float64]:
    """Typical spacing around each point: median distance to its k nearest points.

    This deliberately measures the points rather than the edges. Deriving local
    scale from incident edge lengths -- the obvious approach -- fails exactly
    where it matters: at a node facing an estuary, the edges crossing the water
    outnumber the local ones, so they become the median and the statistic meant
    to detect them is set by them instead. Nearest-neighbour distances cannot be
    poisoned that way, because they do not depend on the edge set being judged.
    """
    points = np.column_stack([eastings, northings]).astype(np.float64)
    k = min(neighbours, len(points) - 1)
    # The first column of the query result is each point's distance to itself.
    distances, _ = KDTree(points).query(points, k=k + 1)
    return np.median(distances[:, 1:], axis=1)


def prune_long_edges(
    edges: Edges,
    eastings: Coordinates,
    northings: Coordinates,
    *,
    alpha: float = DEFAULT_ALPHA,
) -> tuple[Edges, Edges]:
    """Split ``edges`` into those kept and those pruned as implausibly long.

    An edge is pruned when it is longer than ``alpha`` times the local scale of
    its sparser endpoint. Taking the larger of the two scales is deliberate: an
    edge running from a dense centre out to a sparse fringe is normal for the
    fringe, and judging it by the dense end alone would cut the fringe off from
    everything around it.
    """
    lengths = edge_lengths(edges, eastings, northings)
    scale = local_scale(eastings, northings)

    threshold = alpha * np.maximum(scale[edges[:, 0]], scale[edges[:, 1]])
    too_long = lengths > threshold
    return edges[~too_long], edges[too_long]
