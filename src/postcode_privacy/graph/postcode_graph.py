"""A postcode graph: the nodes, how they connect, and how many people live there."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from postcode_privacy._types import Edges
from postcode_privacy.graph.adjacency import Adjacency
from postcode_privacy.postcodes import UnknownPostcodeError, normalise


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
    ) -> PostcodeGraph:
        return cls(
            postcodes=postcodes,
            adjacency=Adjacency.from_edges(edges, n_nodes=len(postcodes)),
            prior=prior,
        )

    @property
    def n_nodes(self) -> int:
        return len(self.postcodes)

    def index_of(self, postcode: str) -> int:
        """The node index of ``postcode``, however it was spelled."""
        canonical = normalise(postcode)
        position = int(np.searchsorted(self.postcodes, canonical))
        if position >= len(self.postcodes) or self.postcodes[position] != canonical:
            raise UnknownPostcodeError(
                f"{canonical} is not a live postcode in this graph"
            )
        return position

    def __contains__(self, postcode: str) -> bool:
        try:
            self.index_of(postcode)
        except (UnknownPostcodeError, ValueError):
            return False
        return True
