"""Turning postcode grid references into an adjacency graph.

Delaunay triangulation is the natural "who is my neighbour" relation for
irregularly spaced points: it is planar, and its mean degree is about six
regardless of local density. That density independence is the property the whole
design rests on -- one hop means roughly the same thing in a city as in a glen,
even though it means wildly different numbers of metres.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay

from postcode_privacy._types import Coordinates, Edges


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
