"""Saving and loading a built graph.

Building from ONSPD takes about forty seconds and 1.4 GB of input, so the
artefact is what makes the library usable more than once. It carries its own
provenance, because a perturbed dataset is only reproducible if you can say
which graph produced it.
"""

from pathlib import Path

import numpy as np
import pytest

from postcode_privacy import PostcodeGraph
from postcode_privacy.graph.artefact import (
    ArtefactVersionMismatchError,
    load_graph,
    save_graph,
)
from postcode_privacy.graph.provenance import SCHEMA_VERSION, Provenance

POSTCODES = np.array(["AA1 1AA", "BB1 1BB", "CC1 1CC", "DD1 1DD"])
EDGES = np.array([[0, 1], [1, 2], [2, 3]], dtype=np.int64)


def a_graph() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=POSTCODES,
        edges=EDGES,
        prior=np.array([5, 1, 9, 2], dtype=np.int64),
        eastings=np.array([100, 200, 300, 400], dtype=np.int64),
        northings=np.array([900, 800, 700, 600], dtype=np.int64),
    )


def a_provenance() -> Provenance:
    return Provenance(
        source="ONSPD_AUG_2026_UK.csv",
        source_sha256="ab51f1e8" * 8,
        gb_only=False,
        prune_alpha=None,
        library_version="0.1.0.dev0",
    )


def test_a_graph_survives_a_round_trip_unchanged(tmp_path: Path) -> None:
    graph = a_graph()
    path = tmp_path / "test.ppg"

    save_graph(graph, path, provenance=a_provenance())
    restored = load_graph(path)

    np.testing.assert_array_equal(restored.postcodes, graph.postcodes)
    np.testing.assert_array_equal(restored.prior, graph.prior)
    np.testing.assert_array_equal(restored.eastings, graph.eastings)
    np.testing.assert_array_equal(restored.northings, graph.northings)
    np.testing.assert_array_equal(restored.adjacency.indptr, graph.adjacency.indptr)
    np.testing.assert_array_equal(restored.adjacency.indices, graph.adjacency.indices)


def test_neighbours_are_preserved_exactly(tmp_path: Path) -> None:
    # Node order is the privacy contract: if a round trip permuted the graph,
    # every subject's output would change silently.
    graph = a_graph()
    path = tmp_path / "test.ppg"
    save_graph(graph, path, provenance=a_provenance())

    restored = load_graph(path)

    for node in range(graph.n_nodes):
        assert sorted(restored.adjacency.neighbours(node)) == sorted(
            graph.adjacency.neighbours(node)
        )


def test_provenance_is_carried_with_the_graph(tmp_path: Path) -> None:
    # A perturbed dataset is only reproducible if the graph that produced it can
    # be identified later.
    path = tmp_path / "test.ppg"
    save_graph(a_graph(), path, provenance=a_provenance())

    restored = load_graph(path)

    assert restored.provenance is not None
    assert restored.provenance.source == "ONSPD_AUG_2026_UK.csv"
    assert restored.provenance.source_sha256.startswith("ab51f1e8")
    assert restored.provenance.schema_version == SCHEMA_VERSION


def test_an_artefact_from_another_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "test.ppg"
    save_graph(a_graph(), path, provenance=a_provenance())

    contents = dict(np.load(path, allow_pickle=False))
    contents["metadata"] = np.array(
        '{"schema_version": 999, "source": "x", "source_sha256": "y", '
        '"gb_only": false, "prune_alpha": null, "library_version": "z"}'
    )
    # Through a handle: savez appends ".npz" to a bare path.
    with path.open("wb") as handle:
        np.savez(handle, **contents)

    with pytest.raises(ArtefactVersionMismatchError, match="999"):
        load_graph(path)


def test_excluded_postcodes_survive_the_round_trip(tmp_path: Path) -> None:
    # Without these, a reloaded graph would tell a caller that a large-user
    # postcode does not exist, which is both wrong and unhelpful.
    graph = PostcodeGraph.from_edges(
        postcodes=POSTCODES,
        edges=EDGES,
        prior=np.array([5, 1, 9, 2], dtype=np.int64),
        excluded=np.array(["ZZ9 9ZZ", "ZZ9 9ZY"]),
        eastings=np.array([100, 200, 300, 400], dtype=np.int64),
        northings=np.array([900, 800, 700, 600], dtype=np.int64),
    )
    path = tmp_path / "test.ppg"
    save_graph(graph, path, provenance=a_provenance())

    restored = load_graph(path)

    assert restored.excluded is not None
    assert sorted(restored.excluded) == ["ZZ9 9ZY", "ZZ9 9ZZ"]
