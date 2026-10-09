"""Shared fixtures."""

from pathlib import Path

import numpy as np
import pytest

from postcode_privacy import PostcodeGraph, Provenance, save_graph

RING_POSTCODES = ["AA1 1AA", "BB1 1BB", "CC1 1CC", "DD1 1DD", "EE1 1EE", "FF1 1FF"]
RING_EDGES = np.array([[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [0, 5]], dtype=np.int64)


@pytest.fixture
def artefact(tmp_path: Path) -> Path:
    """A tiny saved graph, standing in for a real national build."""
    graph = PostcodeGraph.from_edges(
        postcodes=np.array(RING_POSTCODES),
        edges=RING_EDGES,
        prior=np.arange(1, 7, dtype=np.int64),
        excluded=np.array(["ZZ9 9ZZ"]),
        eastings=np.arange(6, dtype=np.int64) * 100,
        northings=np.zeros(6, dtype=np.int64),
    )
    path = tmp_path / "test.ppg"
    save_graph(
        graph,
        path,
        provenance=Provenance(
            source="ONSPD_TEST",
            source_sha256="a" * 64,
            gb_only=True,
            max_edge_km=None,
            prune_alpha=None,
            library_version="0.0.0",
            prior_kind="uniform",
            prior_total=1,
        ),
    )
    return path


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "secret.key"
    path.write_bytes(bytes(range(32)))
    return path


@pytest.fixture
def records(tmp_path: Path) -> Path:
    path = tmp_path / "people.csv"
    path.write_text(
        "patient_id,postcode,age\np1,AA1 1AA,41\np2,CC1 1CC,62\np3,AA1 1AA,19\n"
    )
    return path
