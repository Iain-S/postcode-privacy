"""The mechanism's output distribution for a single postcode.

The weight of an output ``y`` is ``prior(y) * q**min(d(x, y), R)`` where
``q = exp(-epsilon / 2)``. Two facts about that expression shape the whole
implementation.

**It factorises by hop distance.** Every node at the same distance shares the
same exponential factor, so the distribution is a mixture: choose a shell with
probability proportional to the shell's total prior times its factor, then choose
a node within the shell proportional to the prior alone.

That decomposition is not a convenience, it is what makes exact integer
arithmetic possible. A single flat cumulative distribution over the whole country
spans the total prior mass (about 2**26 people) times the dynamic range of the
exponential (``exp(epsilon * R / 2)``) times whatever precision the smallest
weights need. At every usable pair of parameters that exceeds 2**64, so a uint64
cumulative distribution cannot represent it and a float one reintroduces exactly
the leakage integers were chosen to avoid.

Split in two, neither stage is large. The shell stage has only ``R + 1`` entries,
so it can afford exact arbitrary-precision integers. The within-shell stage is
proportional to the prior alone, which is already integral and sums to something
small. The only rounding anywhere is in the powers of ``q``, held to 64 bits of
relative precision.

**Nodes beyond the cap all share one factor.** ``min(d, R)`` means everything at
distance ``R`` or more has factor ``q**R``, so their combined weight follows from
the total prior without enumerating them. Every postcode in the country keeps
non-zero probability, which is what keeps the guarantee pure rather than
approximate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from postcode_privacy.graph.adjacency import Adjacency

# Relative precision held in the powers of q, beyond whatever the exponent
# itself requires. Python integers are unbounded, so this costs only arithmetic
# width and removes any coupling between epsilon, the radius and the arithmetic.
PRECISION_BITS = 64


class PriorError(ValueError):
    """Raised when a prior cannot support a well-defined mechanism."""


@dataclass(frozen=True)
class Distribution:
    """The exact output distribution for one input postcode.

    This is the auditable object: it is the mechanism itself rather than a sample
    from it, so tests and reviewers can interrogate it directly.
    """

    source: int
    radius: int
    shell_nodes: tuple[npt.NDArray[np.int64], ...]
    shell_weights: tuple[int, ...]
    tail_weight: int
    tail_prior: int
    prior: npt.NDArray[np.int64]
    powers: tuple[int, ...]
    ball: npt.NDArray[np.int64]
    prior_cumulative: npt.NDArray[np.int64]

    def contains(self, node: int) -> bool:
        """Whether ``node`` lies inside the ball, and so not in the tail."""
        position = int(np.searchsorted(self.ball, node))
        return position < len(self.ball) and int(self.ball[position]) == node

    @property
    def total_weight(self) -> int:
        return sum(self.shell_weights) + self.tail_weight

    @property
    def teleport_probability(self) -> float:
        """Chance of landing beyond the cap, anywhere in the country.

        A radius that is too small does not error; it quietly inflates this.
        """
        return self.tail_weight / self.total_weight

    @property
    def self_probability(self) -> float:
        """Chance of returning the true postcode unchanged.

        Close to one means the mechanism is handing back the secret, which is
        what an isolated or near-isolated node produces.
        """
        return int(self.prior[self.source]) * self.powers[0] / self.total_weight

    def as_array(self, n_nodes: int) -> npt.NDArray[np.float64]:
        """Probabilities over every node. For inspection and tests, not sampling."""
        weights = np.full(n_nodes, float(self.powers[self.radius]))
        for hop, nodes in enumerate(self.shell_nodes):
            weights[nodes] = float(self.powers[hop])
        weights *= self.prior.astype(np.float64)
        return weights / weights.sum()


def _powers(scale: int, radius: int, q_log: float) -> list[int]:
    """``round(2**scale * q**h)`` for ``h`` in ``0..radius``, as exact integers."""
    unit = 1 << scale
    return [round(unit * math.exp(q_log * hop)) for hop in range(radius + 1)]


def distribution(
    adjacency: Adjacency,
    prior: npt.NDArray[np.int64],
    *,
    source: int,
    epsilon: float,
    radius: int,
) -> Distribution:
    """The exact mechanism distribution for ``source``."""
    if radius < 1:
        raise ValueError("radius must be at least 1")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if np.min(prior) < 1:
        raise PriorError(
            "every node needs a prior of at least 1; a node with zero prior can "
            "never be produced, which would leave it unable to hide anyone"
        )

    q_log = -epsilon / 2
    # Enough bits that the smallest factor, q**radius, still carries full
    # precision rather than collapsing towards zero.
    scale = math.ceil(-q_log * radius * math.log2(math.e)) + PRECISION_BITS
    powers = _powers(scale, radius, q_log)

    # The ball is taken to radius - 1: everything at distance radius or beyond
    # shares the capped factor and is handled in aggregate.
    nodes, hops = adjacency.ball(source=source, radius=radius - 1)

    shell_nodes = tuple(nodes[hops == hop] for hop in range(radius))
    shell_priors = tuple(int(prior[shell].sum()) for shell in shell_nodes)
    shell_weights = tuple(
        prior_sum * powers[hop] for hop, prior_sum in enumerate(shell_priors)
    )

    tail_prior = int(prior.sum()) - sum(shell_priors)
    return Distribution(
        source=source,
        radius=radius,
        shell_nodes=shell_nodes,
        shell_weights=shell_weights,
        tail_weight=tail_prior * powers[radius],
        tail_prior=tail_prior,
        prior=prior,
        powers=tuple(powers),
        ball=np.sort(nodes),
        prior_cumulative=np.cumsum(prior),
    )
