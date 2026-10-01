"""Assembling the graph end to end.

Pruning is off by default. It relies on a geometric threshold that cannot
distinguish an estuary from an empty moor -- the information is simply not in a
point set -- so v1 ships the unmodified triangulation and measures what the
artefacts cost rather than guessing at a parameter.
"""

import numpy as np

from postcode_privacy.graph.build import assemble, delaunay_edges


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
