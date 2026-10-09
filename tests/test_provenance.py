"""Provenance has to tell two graphs apart, or a release cannot be explained.

The failure this guards against is quiet: two artefacts built from the same
ONSPD with different population inputs produce different outputs for every
subject, and until the fields below existed they carried identical provenance.
A manifest that cannot distinguish them cannot support the reproduction claim
made in the README.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from postcode_privacy.graph.artefact import load_graph, save_graph
from postcode_privacy.graph.postcode_graph import PostcodeGraph
from postcode_privacy.graph.provenance import (
    PopulationSource,
    Provenance,
    build_dependencies,
)


def a_graph(prior: list[int]) -> PostcodeGraph:
    n = len(prior)
    return PostcodeGraph.from_edges(
        postcodes=np.array([f"A{i:03d} 1AA" for i in range(n)]),
        edges=np.array([[i, i + 1] for i in range(n - 1)], dtype=np.int64),
        prior=np.array(prior, dtype=np.int64),
        eastings=np.arange(n, dtype=np.int64) * 100,
        northings=np.zeros(n, dtype=np.int64),
    )


def a_provenance(**overrides: object) -> Provenance:
    fields: dict[str, object] = {
        "source": "ONSPD_AUG_2026.csv",
        "source_sha256": "a" * 64,
        "gb_only": False,
        "max_edge_km": 50.0,
        "prune_alpha": None,
        "library_version": "test",
        "prior_kind": "population",
        "prior_total": 67_000_000,
        "population_sources": (
            PopulationSource(name="oa.csv", role="area", sha256="b" * 64),
        ),
        "build_dependencies": build_dependencies(),
    }
    fields.update(overrides)
    return Provenance(**fields)  # ty: ignore[invalid-argument-type]


def test_two_priors_over_one_onspd_are_distinguishable() -> None:
    population = a_provenance()
    uniform = a_provenance(prior_kind="uniform", prior_total=3, population_sources=())

    assert population.source_sha256 == uniform.source_sha256
    assert asdict(population) != asdict(uniform)


def test_two_population_files_over_one_onspd_are_distinguishable() -> None:
    """The case the hashes exist for: same ONSPD, same flags, different inputs.

    Without the input hashes these two differ only in `prior_total`, which a
    revised census release could leave unchanged while moving people between
    postcodes -- and moving people between postcodes changes outputs.
    """
    first = a_provenance()
    second = a_provenance(
        population_sources=(
            PopulationSource(name="oa.csv", role="area", sha256="c" * 64),
        )
    )

    assert asdict(first) != asdict(second)


def test_provenance_survives_the_artefact_round_trip(tmp_path: Path) -> None:
    """Nested population sources have to come back as objects, not dicts.

    `asdict` flattens them on the way out, so loading has to rebuild them or
    the manifest written by a later `perturb` differs in shape from the one
    written by `build` for the same graph.
    """
    path = tmp_path / "graph.ppg"
    provenance = a_provenance()
    save_graph(a_graph([1, 2, 3]), path, provenance=provenance)

    reloaded = load_graph(path).provenance

    assert reloaded == provenance
    assert isinstance(reloaded.population_sources[0], PopulationSource)


def test_build_dependencies_names_what_shapes_the_graph() -> None:
    """Delaunay and the Irish Grid reprojection both live in dependencies.

    A scipy or pyproj change can move an edge or a coordinate without anything
    in this repository changing, so rebuilding an identical artefact needs
    their versions recorded.
    """
    recorded = build_dependencies()

    assert set(recorded) == {"numpy", "scipy", "pyproj"}
    assert all(value for value in recorded.values())


def test_an_older_artefact_is_refused_rather_than_misread(tmp_path: Path) -> None:
    """Schema 2 artefacts have no prior kind, so they cannot answer the question.

    Loading one as though it did would let a release manifest claim a
    population prior for a graph nobody can show was built with one.
    """
    path = tmp_path / "graph.ppg"
    save_graph(a_graph([1, 2, 3]), path, provenance=a_provenance())

    with np.load(path, allow_pickle=False) as stored:
        contents = dict(stored)
    metadata = json.loads(str(contents["metadata"]))
    metadata["schema_version"] = 2
    contents["metadata"] = np.array(json.dumps(metadata))
    with path.open("wb") as handle:
        np.savez_compressed(handle, **contents)

    with pytest.raises(ValueError, match="schema version"):
        load_graph(path)
