"""Where a graph came from, and how it was built.

A perturbed release is only explainable if the graph that produced it can be
identified afterwards, and "identified" has to mean *uniquely*. Two artefacts
built from one ONSPD with different population inputs give every subject a
different output, so provenance that records only the ONSPD hash describes both
equally well and neither usefully. Everything that can move an output is
therefore recorded here: the prior's kind, the hash of every file that fed it,
and the versions of the dependencies that shape the geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version

# Bumped whenever the stored layout changes in a way that would make an older
# artefact load incorrectly rather than fail.
# 2: provenance records max_edge_km. Artefacts written before it were built
# without the absolute edge cut, so they cannot be read as though they had it.
# 3: provenance records the prior kind, the population inputs and the build
# dependency versions. An artefact written before it cannot say which prior it
# carries, and guessing would let a release manifest claim a population prior
# for a graph nobody can show was built with one.
SCHEMA_VERSION = 3

# Dependencies whose version can change the graph without anything in this
# repository changing: scipy triangulates, pyproj reprojects Northern Ireland
# out of the Irish Grid, numpy decides the arithmetic underneath both.
BUILD_DEPENDENCIES = ("numpy", "scipy", "pyproj")


def build_dependencies() -> dict[str, str]:
    """Installed versions of the packages that shape graph construction."""
    found = {}
    for name in BUILD_DEPENDENCIES:
        try:
            found[name] = version(name)
        except PackageNotFoundError:  # pragma: no cover - all three are required
            found[name] = "unknown"
    return found


@dataclass(frozen=True)
class PopulationSource:
    """One file that contributed to the population prior.

    ``role`` is ``"area"`` or ``"postcode"``, because the same file read at the
    two resolutions produces different priors and the name alone does not say
    which was used.
    """

    name: str
    role: str
    sha256: str


@dataclass(frozen=True)
class Provenance:
    """Identifies the inputs and settings a graph was built from."""

    source: str
    source_sha256: str
    gb_only: bool
    max_edge_km: float | None
    prune_alpha: float | None
    library_version: str
    prior_kind: str
    prior_total: int
    population_sources: tuple[PopulationSource, ...] = ()
    build_dependencies: dict[str, str] = field(default_factory=build_dependencies)
    schema_version: int = field(default=SCHEMA_VERSION)

    @classmethod
    def from_metadata(cls, metadata: dict[str, object]) -> Provenance:
        """Rebuild from the JSON ``asdict`` wrote, nested sources included."""
        fields = dict(metadata)
        sources = fields.get("population_sources") or ()
        fields["population_sources"] = tuple(
            PopulationSource(**source)
            for source in sources  # ty: ignore[not-iterable]
        )
        return cls(**fields)  # ty: ignore[invalid-argument-type]
