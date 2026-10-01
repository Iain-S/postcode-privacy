"""The public mechanism: a postcode in, a different real postcode out."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from postcode_privacy.graph.postcode_graph import PostcodeGraph
from postcode_privacy.mechanism.hop import Distribution, distribution
from postcode_privacy.mechanism.prf import Key
from postcode_privacy.mechanism.sample import sample

DEFAULT_MAX_TELEPORT = 1e-6


def radius_for(
    *, epsilon: float, total_prior: int, min_prior: int, max_teleport: float
) -> int:
    """The smallest radius holding the teleport probability under ``max_teleport``.

    Teleport probability is the chance of landing beyond the cap, anywhere in the
    country. A radius that is too small does not error -- it quietly inflates
    this, which is a silent utility disaster rather than a visible failure -- so
    the default is derived rather than guessed.

    The bound is deliberately conservative. A node's tail weight is at most the
    whole national prior times ``q**radius``, while its total weight is at least
    its own prior, so holding ``total_prior * q**radius / min_prior`` under the
    target bounds every node at once without inspecting any of them.
    """
    slack = math.log(total_prior / (min_prior * max_teleport))
    return max(1, math.ceil(2 * slack / epsilon))


@dataclass(frozen=True)
class PostcodeReport:
    """What the mechanism does to one postcode, in terms a person can act on."""

    postcode: str
    epsilon: float
    radius: int
    teleport_probability: float
    self_probability: float
    ball_size: int


class HopMechanism:
    """Metric differential privacy over postcode-graph hop distance."""

    def __init__(
        self,
        graph: PostcodeGraph,
        *,
        epsilon: float,
        radius: int | None = None,
        max_teleport: float = DEFAULT_MAX_TELEPORT,
    ) -> None:
        if epsilon <= 0:
            raise ValueError("epsilon must be positive")
        self.graph = graph
        self.epsilon = epsilon
        self.max_teleport = max_teleport
        self.radius = radius or radius_for(
            epsilon=epsilon,
            total_prior=int(np.sum(graph.prior)),
            min_prior=int(np.min(graph.prior)),
            max_teleport=max_teleport,
        )
        # Datasets hold far fewer distinct postcodes than rows, so the expensive
        # part -- expanding the ball -- is paid once per postcode, not per person.
        self._cache: dict[int, Distribution] = {}

    def distribution(self, postcode: str) -> Distribution:
        """The exact output distribution for ``postcode``."""
        node = self.graph.index_of(postcode)
        if node not in self._cache:
            self._cache[node] = distribution(
                self.graph.adjacency,
                self.graph.prior,
                source=node,
                epsilon=self.epsilon,
                radius=self.radius,
            )
        return self._cache[node]

    def perturb(self, postcode: str, *, subject_id: str, key: Key) -> str:
        """A real postcode standing in for ``postcode``, fixed for this subject."""
        if not subject_id:
            raise ValueError(
                "a subject_id is required: without a stable identifier the same "
                "person cannot be given a consistent output, and repeated "
                "releases would spend the privacy budget over and over"
            )
        dist = self.distribution(postcode)
        node = sample(
            dist,
            key=key,
            fields=(
                subject_id.encode(),
                str(self.graph.postcodes[dist.source]).encode(),
            ),
        )
        return str(self.graph.postcodes[node])

    def report(self, postcode: str) -> PostcodeReport:
        """A summary of what the mechanism does to one postcode."""
        dist = self.distribution(postcode)
        return PostcodeReport(
            postcode=str(self.graph.postcodes[dist.source]),
            epsilon=self.epsilon,
            radius=self.radius,
            teleport_probability=dist.teleport_probability,
            self_probability=dist.self_probability,
            ball_size=len(dist.ball),
        )
