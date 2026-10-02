"""Adversary simulations against the mechanism.

These exist so that the library's claims can be checked rather than believed.
Nothing here is imported by the mechanism itself; it is measurement code, and
its numbers belong in documentation beside the assertions they support.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from postcode_privacy.mechanism.mechanism import HopMechanism
from postcode_privacy.mechanism.prf import Key
from postcode_privacy.mechanism.sample import sample

METRES_PER_KM = 1000.0


@dataclass(frozen=True)
class AttackResult:
    """What an adversary learned from a set of releases."""

    postcode: str
    releases: int
    distinct_outputs: int
    estimate: str
    error_km: float


def posterior(mechanism: HopMechanism, output: str) -> dict[str, float]:
    """An attacker's belief about the true postcode, having seen ``output``.

    Bayes with the population prior as the attacker's own: the posterior is
    proportional to ``prior(x) * K(x)(output)``. Both factors are computed
    exactly, including each candidate's normaliser, because approximating the
    normaliser away would quietly change the answer in the attacker's favour or
    against it, and the point of this function is to be trusted.

    Candidates are the postcodes within the ball around ``output``. Everything
    outside it shares the floor weight, so including them would add a uniform
    smear that cannot change which candidate ranks highest -- but it does mean
    the cost is one distribution per candidate, which is why this is a research
    tool and not something to run over a nation.
    """
    graph = mechanism.graph
    target = graph.index_of(output)
    neighbourhood = mechanism.distribution(output).ball

    beliefs: dict[str, float] = {}
    for node in neighbourhood.tolist():
        candidate = str(graph.postcodes[node])
        distribution = mechanism.distribution(candidate)
        likelihood = distribution.probability_of(target)
        beliefs[candidate] = float(graph.prior[node]) * likelihood

    total = sum(beliefs.values())
    return {name: weight / total for name, weight in beliefs.items()}


def averaging_attack(
    mechanism: HopMechanism,
    postcode: str,
    *,
    releases: int,
    keyed: bool,
    key: Key | None = None,
    seed: int = 0,
) -> AttackResult:
    """Observe ``releases`` outputs for one subject and average them.

    This is the attack that keyed determinism exists to defeat. Under fresh
    randomness the mean of enough outputs converges on the true location, so
    repeated publication of the same person destroys the guarantee. Under the
    keyed mechanism every release is identical, so a thousand observations are
    worth exactly one.
    """
    graph = mechanism.graph
    if graph.eastings is None or graph.northings is None:
        raise ValueError("the averaging attack needs a graph with coordinates")

    distribution = mechanism.distribution(postcode)
    rng = np.random.default_rng(seed)

    if keyed:
        if key is None:
            raise ValueError("a keyed attack needs the key the releases used")
        # One subject, one key: every release is the same draw by construction.
        drawn = sample(
            distribution,
            key=key,
            fields=(b"subject", postcode.encode()),
            prior_cumulative=graph.prior_cumulative,
        )
        outputs = [str(graph.postcodes[drawn])] * releases
    else:
        # Fresh randomness per release, which is what the keyed design refuses
        # to do: a different key each time stands in for an independent draw.
        outputs = [
            str(
                graph.postcodes[
                    sample(
                        distribution,
                        key=Key.from_bytes(bytes(rng.integers(0, 256, 32).tolist())),
                        fields=(b"subject", postcode.encode()),
                        prior_cumulative=graph.prior_cumulative,
                    )
                ]
            )
            for _ in range(releases)
        ]

    indices = [graph.index_of(name) for name in outputs]
    centre = np.array(
        [
            float(np.mean(graph.eastings[indices])),
            float(np.mean(graph.northings[indices])),
        ]
    )
    # The attacker's best guess is the real postcode nearest their estimate.
    points = np.column_stack([graph.eastings, graph.northings]).astype(np.float64)
    nearest = int(np.argmin(np.linalg.norm(points - centre, axis=1)))

    truth = graph.index_of(postcode)
    error = float(np.linalg.norm(points[nearest] - points[truth])) / METRES_PER_KM
    return AttackResult(
        postcode=postcode,
        releases=releases,
        distinct_outputs=len(set(outputs)),
        estimate=str(graph.postcodes[nearest]),
        error_km=error,
    )
