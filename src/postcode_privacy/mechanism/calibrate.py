"""Turning epsilon into something a person can decide about.

Epsilon is a rate per hop, and nobody has intuition for it. These helpers
measure what a given epsilon actually does to a graph, and solve the inverse
problem: the epsilon that meets a stated utility or privacy target.

Displacement is always reported *conditional on not teleporting*, with the
teleport probability beside it. Mixing the two would hide a radius that is too
small, because a handful of country-wide jumps would drag the average up and
look like ordinary local spread.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from postcode_privacy.graph.postcode_graph import PostcodeGraph
from postcode_privacy.mechanism.mechanism import HopMechanism

METRES_PER_KM = 1000.0

# Bracketing range for the solver. The lower bound is not arbitrary: below
# roughly 0.05 per hop the derived radius grows until the ball is the entire
# country, so each evaluation costs orders of magnitude more while describing a
# mechanism that is barely distinguishable from drawing straight from the prior.
# A target that can only be met outside this range is reported as unreachable
# rather than quietly answered with a number nobody should use.
MIN_EPSILON = 0.05
MAX_EPSILON = 50.0
# Geometric bisection over [1e-3, 50] narrows the bracket by 2**-n of five
# decades, so twenty steps resolve epsilon to about one part in 10**5 --
# far finer than the measurement noise, and each step costs a full pass
# over the sample on a graph of 1.7 million nodes.
SOLVER_ITERATIONS = 20


class UnknownTargetError(ValueError):
    """Raised when a calibration target is not one this library can solve."""


@dataclass(frozen=True)
class DisplacementSummary:
    """How far one postcode's output lands from the truth."""

    postcode: str
    mean_km: float
    median_km: float
    p95_km: float
    self_probability: float
    teleport_probability: float
    ball_size: int


@dataclass(frozen=True)
class CalibrationResult:
    """An epsilon meeting a target, and the evidence it was solved against."""

    target: str
    requested: float
    epsilon: float
    achieved: float
    p95: float
    sample_size: int
    # False when the target lies outside the bracketed range, so the epsilon
    # returned is the closest achievable rather than the one asked for.
    reached: bool


def _weighted_quantile(
    values: npt.NDArray[np.float64], weights: npt.NDArray[np.float64], q: float
) -> float:
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    if cumulative[-1] <= 0:
        return 0.0
    return float(values[int(np.searchsorted(cumulative, q * cumulative[-1]))])


def displacement_summary(mechanism: HopMechanism, postcode: str) -> DisplacementSummary:
    """Distances the output may land from ``postcode``, weighted by probability."""
    graph = mechanism.graph
    if graph.eastings is None or graph.northings is None:
        raise ValueError("displacement needs a graph built with coordinates")

    distribution = mechanism.distribution(postcode)
    source = graph.index_of(postcode)

    # `powers` carries one entry more than there are shells: the last is the
    # floor weight applied to everything beyond the cap. Slicing explicitly and
    # pairing strictly says so, where a lenient zip would silently drop a shell
    # if that relationship ever changed.
    shells = distribution.shell_nodes
    shell_powers = distribution.powers[: len(shells)]
    nodes = np.concatenate(shells)
    weights = np.concatenate(
        [
            graph.prior[shell].astype(np.float64) * float(power)
            for shell, power in zip(shells, shell_powers, strict=True)
        ]
    )
    offsets = np.column_stack(
        [
            graph.eastings[nodes] - graph.eastings[source],
            graph.northings[nodes] - graph.northings[source],
        ]
    ).astype(np.float64)
    distances = np.linalg.norm(offsets, axis=1) / METRES_PER_KM

    total = float(weights.sum())
    return DisplacementSummary(
        postcode=postcode,
        mean_km=float((distances * weights).sum() / total) if total else 0.0,
        median_km=_weighted_quantile(distances, weights, 0.5),
        p95_km=_weighted_quantile(distances, weights, 0.95),
        self_probability=distribution.self_probability,
        teleport_probability=distribution.teleport_probability,
        ball_size=len(distribution.ball),
    )


def sample_postcodes(graph: PostcodeGraph, *, size: int, seed: int) -> list[str]:
    """A reproducible random sample of postcodes to measure against."""
    rng = np.random.default_rng(seed)
    chosen = rng.choice(graph.n_nodes, size=min(size, graph.n_nodes), replace=False)
    return [str(graph.postcodes[index]) for index in chosen]


def _median_displacement(
    graph: PostcodeGraph, epsilon: float, postcodes: list[str]
) -> tuple[float, float]:
    mechanism = HopMechanism(graph, epsilon=epsilon)
    medians = []
    for postcode in postcodes:
        medians.append(displacement_summary(mechanism, postcode).median_km)
        # Each postcode is visited once, and a cached distribution over a
        # national graph costs megabytes, so nothing is kept.
        mechanism.clear_cache()
    return float(np.median(medians)), float(np.quantile(medians, 0.95))


def _max_self_probability(
    graph: PostcodeGraph, epsilon: float, postcodes: list[str]
) -> tuple[float, float]:
    mechanism = HopMechanism(graph, epsilon=epsilon)
    values = []
    for postcode in postcodes:
        values.append(mechanism.distribution(postcode).self_probability)
        mechanism.clear_cache()
    return float(np.median(values)), float(np.quantile(values, 0.95))


# Each target maps an epsilon to a measured value. All are monotonic in epsilon,
# which is what makes bisection valid; `increasing` records the direction.
TARGETS = {
    "median-displacement-km": (_median_displacement, False),
    "max-self-probability": (_max_self_probability, True),
}


def calibrate(
    graph: PostcodeGraph,
    *,
    target: str,
    value: float,
    sample_size: int = 16,
    seed: int = 0,
    progress: Callable[[int, int], None] | None = None,
) -> CalibrationResult:
    """Solve for the epsilon meeting ``target`` at ``value``.

    Bisection, which is valid because every target is monotonic in epsilon:
    raising epsilon moves people less far and hands back the true postcode more
    often. The answer is a property of the sample, not of the country, so the
    spread it was solved against travels with it.
    """
    if target not in TARGETS:
        raise UnknownTargetError(
            f"unknown target {target!r}; available targets are "
            f"{', '.join(sorted(TARGETS))}"
        )
    measure, increasing = TARGETS[target]
    postcodes = sample_postcodes(graph, size=sample_size, seed=seed)

    # Both ends are measured first, so a target outside the achievable range is
    # reported as such instead of being answered with a bracket endpoint.
    at_min, _ = measure(graph, MIN_EPSILON, postcodes)
    at_max, _ = measure(graph, MAX_EPSILON, postcodes)
    lowest, highest = min(at_min, at_max), max(at_min, at_max)
    reached = lowest <= value <= highest

    low, high = MIN_EPSILON, MAX_EPSILON
    for step in range(SOLVER_ITERATIONS):
        if progress is not None:
            progress(step + 1, SOLVER_ITERATIONS)
        middle = math.sqrt(low * high)  # geometric: epsilon spans decades
        achieved, _ = measure(graph, middle, postcodes)
        too_high = achieved > value if increasing else achieved < value
        if too_high:
            high = middle
        else:
            low = middle

    epsilon = high if increasing else low
    achieved, spread = measure(graph, epsilon, postcodes)
    return CalibrationResult(
        target=target,
        requested=value,
        epsilon=epsilon,
        achieved=achieved,
        p95=spread,
        sample_size=len(postcodes),
        reached=reached,
    )
