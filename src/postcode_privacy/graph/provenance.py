"""Where a graph came from, and how it was built."""

from __future__ import annotations

from dataclasses import dataclass, field

# Bumped whenever the stored layout changes in a way that would make an older
# artefact load incorrectly rather than fail.
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Provenance:
    """Identifies the inputs and settings a graph was built from.

    A perturbed dataset is only reproducible if the graph that produced it can
    be identified afterwards, so this travels with the artefact.
    """

    source: str
    source_sha256: str
    gb_only: bool
    prune_alpha: float | None
    library_version: str
    schema_version: int = field(default=SCHEMA_VERSION)
