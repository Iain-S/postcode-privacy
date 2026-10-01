"""Drawing one output postcode from a distribution.

Two stages, matching the way the distribution factorises. First choose a shell --
a ring of postcodes all the same number of hops away, and therefore all carrying
the same exponential factor. Then choose a postcode within that ring, in
proportion to the prior alone.

Everything here is a pure function of integers drawn from the PRF, so the
sampler is deterministic in the subject and almost entirely testable by
enumeration.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from itertools import accumulate

import numpy as np
import numpy.typing as npt

from postcode_privacy.mechanism.hop import Distribution
from postcode_privacy.mechanism.prf import Key

# Rejection when drawing from the tail cannot plausibly recur this often: each
# attempt fails only if it lands inside the ball, which holds a small share of
# the country's prior mass.
MAX_TAIL_ATTEMPTS = 1_000


def choose(cumulative: Sequence[int], draw: int) -> int:
    """Index of the bucket containing ``draw``, given cumulative widths.

    ``bisect_right`` is what makes a zero-width bucket unselectable: its
    cumulative value equals its predecessor's, so no draw can fall between them.
    An empty shell therefore cannot be chosen, and an off-by-one here would skew
    every draw towards one neighbour.
    """
    return bisect_right(cumulative, draw)


def sample(dist: Distribution, *, key: Key, fields: tuple[bytes, ...]) -> int:
    """The output node for one subject, as a deterministic function of ``fields``."""
    shell_cumulative = list(accumulate([*dist.shell_weights, dist.tail_weight]))
    total = shell_cumulative[-1]

    shell = choose(shell_cumulative, key.draw(*fields, b"shell", bound=total))

    if shell < len(dist.shell_nodes):
        return _within(dist.shell_nodes[shell], dist.prior, key, fields, b"node")
    return _from_the_tail(dist, key, fields)


def _within(
    nodes: npt.NDArray[np.int64],
    prior: npt.NDArray[np.int64],
    key: Key,
    fields: tuple[bytes, ...],
    tag: bytes,
) -> int:
    """A node from ``nodes``, in proportion to its prior."""
    cumulative = np.cumsum(prior[nodes])
    draw = key.draw(*fields, tag, bound=int(cumulative[-1]))
    return int(nodes[np.searchsorted(cumulative, draw, side="right")])


def _from_the_tail(dist: Distribution, key: Key, fields: tuple[bytes, ...]) -> int:
    """A node at or beyond the cap, in proportion to its prior.

    Those nodes are never enumerated -- that is the point of capping the metric
    rather than the support -- so instead we draw from the whole country and
    reject anything that turns out to lie inside the ball. The ball holds a small
    share of the national prior, so rejection is rare.
    """
    cumulative = dist.prior_cumulative
    bound = int(cumulative[-1])
    for attempt in range(MAX_TAIL_ATTEMPTS):
        draw = key.draw(*fields, b"tail", attempt.to_bytes(4, "big"), bound=bound)
        node = int(np.searchsorted(cumulative, draw, side="right"))
        if not dist.contains(node):
            return node
    raise RuntimeError("tail rejection sampling failed implausibly often")
