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
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from postcode_privacy.graph.adjacency import Adjacency

# Relative precision held in the powers of q, beyond whatever the exponent
# itself requires. Python integers are unbounded, so this costs only arithmetic
# width and removes any coupling between epsilon, the radius and the arithmetic.
PRECISION_BITS = 64

# Fractional bits in the rational bound on q. Only the ratios between
# consecutive powers matter, and those are exact by construction whatever this
# is; the value decides how close the implemented epsilon is to the requested
# one, not whether the guarantee holds.
Q_BITS = 128

# The sampler accumulates the prior in int64, so the total prior mass is what
# has to fit. Weights themselves are unbounded Python integers.
MAX_TOTAL_PRIOR = 2**62


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

    def probability_of(self, node: int) -> float:
        """The probability of one node, without materialising the rest.

        ``as_array`` allocates a vector the size of the country, which is fine
        for inspection but not for an adversary simulation that needs one entry
        per candidate. Nodes beyond the cap share the floor weight, so a node
        absent from every shell is a tail node rather than an impossible one.
        """
        for hop, nodes in enumerate(self.shell_nodes):
            position = int(np.searchsorted(nodes, node))
            if position < len(nodes) and int(nodes[position]) == node:
                power = self.powers[hop]
                break
        else:
            power = self.powers[self.radius]
        return int(self.prior[node]) * power / self.total_weight

    def as_array(self, n_nodes: int) -> npt.NDArray[np.float64]:
        """Probabilities over every node. For inspection and tests, not sampling."""
        weights = np.full(n_nodes, float(self.powers[self.radius]))
        for hop, nodes in enumerate(self.shell_nodes):
            weights[nodes] = float(self.powers[hop])
        weights *= self.prior.astype(np.float64)
        return weights / weights.sum()


@lru_cache(maxsize=128)
def q_upper_bound(epsilon: float, *, bits: int = Q_BITS) -> Fraction:
    """A dyadic rational provably at least ``exp(-epsilon / 2)``.

    Erring upwards is the safe direction. ``q`` controls how fast the weights
    decay, so a larger ``q`` is a slower decay, which is a *smaller* effective
    epsilon: the mechanism built on this bound satisfies the epsilon that was
    asked for, with a sliver of precision given away rather than taken.

    ``Decimal.exp`` is correctly rounded to the context precision, so the
    60-digit result sits within half an ulp of the truth and the 1e-50 nudge
    covers that with ten orders of magnitude to spare. The multiplication by
    ``0.5`` runs at a precision no double can overflow, so the exponent itself
    is exact rather than rounded in an unknown direction.
    """
    with localcontext() as ctx:
        ctx.prec = 1200
        exponent = Decimal(-epsilon) * Decimal("0.5")
        ctx.prec = 60
        value = (+exponent).exp()
    exact = Fraction(value) * (1 + Fraction(1, 10**50))
    unit = 1 << bits
    numerator = -(-exact.numerator * unit // exact.denominator)  # ceil
    return Fraction(numerator, unit)


def _powers(scale: int, radius: int, q: Fraction) -> list[int]:
    """Integer weights that decay no faster than ``q``, which is what the proof needs.

    The guarantee holds for every ``(x, x', y)`` if and only if the weight of a
    node never falls by more than ``q`` per hop:
    ``P[j + h] >= q**h * P[j]`` for every ``j`` and ``h``. Evaluating each power
    independently -- ``round(2**scale * math.exp(-epsilon / 2 * hop))`` -- does
    not give that. It errs in both directions, and when one hop's error lands
    low after its predecessor's landed high, the implemented ratio exceeds the
    advertised bound. On a two-node graph with a prior spanning the int64 range
    the excess over ``exp(0.3)`` is 1.25e-17: numerically nothing, formally a
    false theorem. The term that mattered was the double rather than the
    rounding -- at epsilon 0.3 the float exponential was off by 4.7e-18
    relative, 170 times one unit in the last place.

    Taking ``q`` as an exact rational and rounding *up*, each power from the one
    before it, makes the inequality hold by construction at every step and so,
    by induction, at every pair. The cost is that the powers are very slightly
    larger than the real ones -- below 1.5e-20 relative across epsilon in
    [0.01, 5] at radius 60 -- which is the direction that gives away utility
    rather than privacy.
    """
    powers = [1 << scale]
    for _ in range(radius):
        powers.append(-(-powers[-1] * q.numerator // q.denominator))
    return powers


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

    # Summed in float first, because an int64 sum of an oversized prior wraps
    # silently and the check would then pass on exactly the input it exists to
    # reject. A double carries the magnitude exactly enough for a comparison
    # with two full bits of headroom below the int64 ceiling.
    if float(np.sum(prior, dtype=np.float64)) > MAX_TOTAL_PRIOR:
        raise PriorError(
            f"total prior mass exceeds the supported maximum of "
            f"{MAX_TOTAL_PRIOR}; the sampler accumulates the prior in int64"
        )
    total_prior = int(prior.sum())

    q = q_upper_bound(epsilon)
    # Enough bits that the smallest factor, q**radius, still carries full
    # precision rather than collapsing towards zero -- plus the bits the
    # rounding-up itself can accumulate, which is bounded by 1 / (1 - q) and
    # grows as epsilon shrinks.
    decay_bits = math.ceil(epsilon / 2 * radius * math.log2(math.e))
    carry_bits = math.ceil(-math.log2(float(1 - q)))
    scale = decay_bits + max(carry_bits, 0) + PRECISION_BITS
    powers = _powers(scale, radius, q)

    # The ball is taken to radius - 1: everything at distance radius or beyond
    # shares the capped factor and is handled in aggregate.
    nodes, hops = adjacency.ball(source=source, radius=radius - 1)

    shell_nodes = tuple(nodes[hops == hop] for hop in range(radius))
    shell_priors = tuple(int(prior[shell].sum()) for shell in shell_nodes)
    shell_weights = tuple(
        prior_sum * powers[hop] for hop, prior_sum in enumerate(shell_priors)
    )

    tail_prior = total_prior - sum(shell_priors)
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
    )
