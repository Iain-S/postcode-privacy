"""Saving a built graph, and loading it back exactly.

Building from ONSPD reads 1.4 GB and takes the better part of a minute, so an
artefact is what makes the library usable more than once. It carries its
provenance because a perturbed dataset is only reproducible if the graph that
produced it can be identified afterwards -- and because node order is the
privacy contract, a round trip that permuted the graph would silently change
every subject's output.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from postcode_privacy.graph.adjacency import Adjacency
from postcode_privacy.graph.postcode_graph import PostcodeGraph
from postcode_privacy.graph.provenance import SCHEMA_VERSION, Provenance

# Eight characters covers every UK postcode in canonical form, the longest
# being seven characters plus the separating space.
POSTCODE_WIDTH = 8


class ArtefactVersionMismatchError(ValueError):
    """Raised when an artefact was written by an incompatible schema."""


def save_graph(
    graph: PostcodeGraph, path: str | Path, *, provenance: Provenance
) -> None:
    """Write ``graph`` to ``path``."""
    if graph.eastings is None or graph.northings is None:
        raise ValueError("a saved graph needs coordinates for evaluation and reports")
    eastings, northings = graph.eastings, graph.northings
    # Written through an open handle because savez_compressed appends ".npz"
    # to a bare path, which would silently rename the artefact.
    with Path(path).open("wb") as handle:
        np.savez_compressed(
            handle,
            metadata=np.array(json.dumps(asdict(provenance))),
            # Stored as bytes rather than numpy's UTF-32 strings, which would cost
            # four times as much for characters that are always ASCII.
            postcodes=graph.postcodes.astype(f"S{POSTCODE_WIDTH}"),
            # Large-user postcodes: not nodes, but remembered so that
            # submitting one is explained rather than denied.
            excluded=(
                graph.excluded
                if graph.excluded is not None
                else np.array([], dtype=np.str_)
            ).astype(f"S{POSTCODE_WIDTH}"),
            prior=graph.prior.astype(np.int32),
            indptr=graph.adjacency.indptr.astype(np.int64),
            indices=graph.adjacency.indices.astype(np.int32),
            eastings=eastings.astype(np.int32),
            northings=northings.astype(np.int32),
        )


def load_graph(path: str | Path) -> PostcodeGraph:
    """Read a graph written by :func:`save_graph`."""
    with np.load(Path(path), allow_pickle=False) as stored:
        metadata = json.loads(str(stored["metadata"]))
        version = metadata.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ArtefactVersionMismatchError(
                f"artefact uses schema version {version}, this library reads "
                f"{SCHEMA_VERSION}; rebuild the graph"
            )

        return PostcodeGraph(
            postcodes=stored["postcodes"].astype(f"<U{POSTCODE_WIDTH}"),
            adjacency=Adjacency(
                indptr=stored["indptr"].astype(np.int64),
                indices=stored["indices"].astype(np.int64),
            ),
            prior=stored["prior"].astype(np.int64),
            excluded=stored["excluded"].astype(f"<U{POSTCODE_WIDTH}"),
            eastings=stored["eastings"].astype(np.int64),
            northings=stored["northings"].astype(np.int64),
            provenance=Provenance.from_metadata(metadata),
        )
