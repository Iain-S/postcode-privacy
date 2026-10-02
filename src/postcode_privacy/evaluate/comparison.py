"""What epsilon is "equivalent" to truncating a postcode?

There is no exact answer, and saying why is half the value. Truncation is not
differential privacy: it releases a fact with certainty and offers no
deniability at any crowd size, so no epsilon makes the two the same object.
Equivalence can only be stated under a chosen yardstick, and the choice is the
finding rather than a detail of it.

The yardstick here is **what an analyst loses**. Told only the outward code, the
best they can do is a postcode drawn from that district, and their expected
error is the population-weighted mean distance from the truth to such a
postcode. The equivalent epsilon is the one at which the mechanism displaces
people about that far.

Two things this deliberately does not do. It does not claim the two give equal
*privacy* -- the yardstick is utility, and every yardstick flatters truncation
by ignoring that its released fact is certain. And it does not produce a single
national number: equivalence is a per-location quantity, because truncation's
protection varies by orders of magnitude between a London district and a
Highland one. The distribution is the result.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from postcode_privacy.graph.postcode_graph import PostcodeGraph
from postcode_privacy.mechanism.calibrate import (
    MAX_EPSILON,
    MIN_EPSILON,
    displacement_summary,
)
from postcode_privacy.mechanism.mechanism import HopMechanism

METRES_PER_KM = 1000.0
SOLVER_ITERATIONS = 18


@dataclass(frozen=True)
class Equivalence:
    """An epsilon matching truncation's cost to the analyst, at one postcode."""

    postcode: str
    outward: str
    district_size: int
    truncation_km: float
    epsilon: float
    achieved_km: float


def outward_groups(
    postcodes: npt.NDArray[np.str_],
) -> dict[str, npt.NDArray[np.int64]]:
    """Node indices grouped by outward code -- the part before the space."""
    collected: dict[str, list[int]] = defaultdict(list)
    for index, postcode in enumerate(postcodes.tolist()):
        collected[postcode.split()[0]].append(index)
    return {
        outward: np.array(members, dtype=np.int64)
        for outward, members in collected.items()
    }


def truncation_error_km(
    graph: PostcodeGraph,
    postcode: str,
    *,
    groups: dict[str, npt.NDArray[np.int64]],
) -> float:
    """Expected error for an analyst given only the outward code.

    Weighted by population, because the analyst's best guess is a *person* drawn
    from the district rather than a postcode drawn uniformly.
    """
    if graph.eastings is None or graph.northings is None:
        raise ValueError("this comparison needs a graph with coordinates")

    source = graph.index_of(postcode)
    members = groups[str(graph.postcodes[source]).split()[0]]
    if len(members) < 2:
        raise ValueError(
            f"{postcode} is alone in its outward code, so truncation hides it "
            "among nobody and no epsilon is equivalent to that"
        )

    offsets = np.column_stack(
        [
            graph.eastings[members] - graph.eastings[source],
            graph.northings[members] - graph.northings[source],
        ]
    ).astype(np.float64)
    distances = np.linalg.norm(offsets, axis=1) / METRES_PER_KM
    weights = graph.prior[members].astype(np.float64)
    return float((distances * weights).sum() / weights.sum())


def equivalent_epsilon(
    graph: PostcodeGraph,
    postcode: str,
    *,
    groups: dict[str, npt.NDArray[np.int64]],
) -> Equivalence:
    """The epsilon at which displacement matches truncation's cost."""
    target = truncation_error_km(graph, postcode, groups=groups)
    outward = str(graph.postcodes[graph.index_of(postcode)]).split()[0]

    low, high = MIN_EPSILON, MAX_EPSILON
    for _ in range(SOLVER_ITERATIONS):
        middle = math.sqrt(low * high)
        mechanism = HopMechanism(graph, epsilon=middle)
        achieved = displacement_summary(mechanism, postcode).median_km
        # Displacement falls as epsilon rises, so overshooting means epsilon is
        # too low.
        if achieved > target:
            low = middle
        else:
            high = middle

    mechanism = HopMechanism(graph, epsilon=high)
    return Equivalence(
        postcode=postcode,
        outward=outward,
        district_size=len(groups[outward]),
        truncation_km=target,
        epsilon=high,
        achieved_km=displacement_summary(mechanism, postcode).median_km,
    )
