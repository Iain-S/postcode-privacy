"""A postcode graph: the nodes, how they connect, and how many people live there."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from postcode_privacy._types import Edges
from postcode_privacy.graph.adjacency import Adjacency
from postcode_privacy.graph.provenance import Provenance
from postcode_privacy.postcodes import (
    LargeUserPostcodeError,
    UnknownPostcodeError,
    normalise,
)


@dataclass(frozen=True)
class PostcodeGraph:
    """Live postcodes, their adjacency, and the prior weight of each.

    Postcodes are held in canonical order, so a node's index is determined by its
    spelling alone. Keyed determinism rests on that: reordering the nodes would
    silently change every subject's output.
    """

    postcodes: npt.NDArray[np.str_]
    adjacency: Adjacency
    prior: npt.NDArray[np.int64]

    # Postcodes that exist but are deliberately not nodes: Royal Mail
    # large-user postcodes, which belong to one organisation and have no
    # resident population. Held so that submitting one gives an explanation
    # rather than "unknown".
    excluded: npt.NDArray[np.str_] | None = None
    eastings: npt.NDArray[np.int64] | None = None
    northings: npt.NDArray[np.int64] | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        # Shared by every distribution drawn from this graph. Held here rather
        # than on each distribution, which is cached per distinct postcode: on
        # the real graph this array is 14 MB, so a copy per postcode would cost
        # gigabytes for a dataset of any size.
        object.__setattr__(self, "prior_cumulative", np.cumsum(self.prior))

    prior_cumulative: npt.NDArray[np.int64] = field(init=False, repr=False)

    @classmethod
    def from_edges(
        cls,
        *,
        postcodes: npt.NDArray[np.str_],
        edges: Edges,
        prior: npt.NDArray[np.int64],
        excluded: npt.NDArray[np.str_] | None = None,
        eastings: npt.NDArray[np.int64] | None = None,
        northings: npt.NDArray[np.int64] | None = None,
        provenance: Provenance | None = None,
    ) -> PostcodeGraph:
        return cls(
            postcodes=postcodes,
            adjacency=Adjacency.from_edges(edges, n_nodes=len(postcodes)),
            prior=prior,
            excluded=excluded,
            eastings=eastings,
            northings=northings,
            provenance=provenance,
        )

    @property
    def n_nodes(self) -> int:
        return len(self.postcodes)

    def index_of(self, postcode: str) -> int:
        """The node index of ``postcode``, however it was spelled."""
        canonical = normalise(postcode)
        position = int(np.searchsorted(self.postcodes, canonical))
        if position >= len(self.postcodes) or self.postcodes[position] != canonical:
            self._explain_absence(canonical)
        return position

    def _explain_absence(self, canonical: str) -> None:
        """Raise the most specific error available for a missing postcode."""
        if self.excluded is not None and len(self.excluded):
            at = int(np.searchsorted(self.excluded, canonical))
            if at < len(self.excluded) and self.excluded[at] == canonical:
                raise LargeUserPostcodeError(
                    f"{canonical} is a Royal Mail large user postcode, belonging "
                    "to a single organisation rather than to residents. It has no "
                    "resident population to hide anyone among, so it is never a "
                    "valid input or output. Use the postcode of the person's home "
                    "address instead."
                )
        raise UnknownPostcodeError(f"{canonical} is not a live postcode in this graph")

    def __contains__(self, postcode: str) -> bool:
        try:
            self.index_of(postcode)
        except (LargeUserPostcodeError, UnknownPostcodeError, ValueError):
            return False
        return True
