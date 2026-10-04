"""Adversary simulations against the mechanism.

These exist so that the library's claims can be checked rather than believed.
Nothing here is imported by the mechanism itself; it is measurement code, and
its numbers belong in documentation beside the assertions they support.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from postcode_privacy.mechanism.mechanism import HopMechanism
from postcode_privacy.mechanism.prf import Key
from postcode_privacy.mechanism.sample import sample
from postcode_privacy.postcodes import normalise


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


def independent_releases(
    mechanism: HopMechanism, postcode: str, *, count: int, seed: int = 0
) -> list[str]:
    """``count`` outputs drawn with fresh randomness each time.

    This is what the library refuses to do, modelled by using a different key
    per release. Each draw is independent evidence about the same secret, so an
    attacker accumulates information with every publication.
    """
    distribution = mechanism.distribution(postcode)
    rng = np.random.default_rng(seed)
    return [
        str(
            mechanism.graph.postcodes[
                sample(
                    distribution,
                    key=Key.from_bytes(bytes(rng.integers(0, 256, 32).tolist())),
                    fields=(b"subject", postcode.encode()),
                    prior_cumulative=mechanism.graph.prior_cumulative,
                )
            ]
        )
        for _ in range(count)
    ]


def keyed_releases(
    mechanism: HopMechanism, postcode: str, *, count: int, key: Key
) -> list[str]:
    """``count`` outputs from the keyed mechanism: the same value every time."""
    drawn = sample(
        mechanism.distribution(postcode),
        key=key,
        fields=(b"subject", postcode.encode()),
        prior_cumulative=mechanism.graph.prior_cumulative,
    )
    return [str(mechanism.graph.postcodes[drawn])] * count


def posterior_after(
    mechanism: HopMechanism,
    outputs: list[str],
    *,
    independent: bool = True,
    candidate_radius: int | None = None,
) -> dict[str, float]:
    """An attacker's belief after seeing every release in ``outputs``.

    Independent releases multiply: the posterior is proportional to
    ``prior(x) * prod_i K(x)(y_i)``, and each draw sharpens the belief.

    ``independent=False`` models an attacker who knows the releases came from
    the keyed mechanism. That matters, and it is not a convenience: under keyed
    determinism one subject has exactly one output, so repeated publications
    are the same value, not repeated samples. An attacker who multiplied them
    anyway would become *more* confident than the evidence supports -- a wrong
    answer, not a conservative one. Assuming the adversary knows the scheme is
    the usual and the safe assumption, so duplicates are counted once.

    This is the attacker the library should be judged against, not a centroid
    of the outputs. A centroid is biased wherever the output cloud is not
    symmetric about the truth, which on real geography means anywhere near a
    coast: measured on the national graph it put a Sutherland resident nearly
    three hundred kilometres out, and did *worse* than seeing one release.

    Candidates are the postcodes near the first observation. Every candidate
    costs its own distribution, so ``candidate_radius`` bounds the work; the
    default uses the mechanism's own ball, which is only tractable on small
    graphs.
    """
    graph = mechanism.graph
    first = graph.index_of(outputs[0])
    if candidate_radius is None:
        candidates = mechanism.distribution(outputs[0]).ball
    else:
        candidates, _ = graph.adjacency.ball(source=first, radius=candidate_radius)

    observed = outputs if independent else list(dict.fromkeys(outputs))
    targets = [graph.index_of(name) for name in observed]
    beliefs: dict[str, float] = {}
    for node in candidates.tolist():
        candidate = str(graph.postcodes[node])
        distribution = mechanism.distribution(candidate)
        # Summed in logs: a product of hundreds of small likelihoods underflows
        # to zero long before the posterior becomes uninteresting.
        log_belief = math.log(float(graph.prior[node]))
        for target in targets:
            log_belief += math.log(distribution.probability_of(target))
        beliefs[candidate] = log_belief

    highest = max(beliefs.values())
    weights = {name: math.exp(value - highest) for name, value in beliefs.items()}
    total = sum(weights.values())
    return {name: weight / total for name, weight in weights.items()}


@dataclass(frozen=True)
class AttackResult:
    """What an adversary concluded, and whether the question was fair.

    ``truth_considered`` is the field that makes the rest meaningful. Candidates
    are drawn from a ball around the observed output, and on a national graph
    the true postcode can lie entirely outside it. A wrong top guess then means
    one of two quite different things -- the attacker was beaten, or the
    attacker was never shown the answer -- and only the first is an attacker
    success rate. When the truth was not considered, the rank and probability
    are ``None`` rather than a number somebody could quote.
    """

    outputs: tuple[str, ...]
    candidates: int
    candidate_radius: int | None
    top_guess: str
    top_probability: float
    truth_considered: bool
    truth_rank: int | None
    truth_probability: float | None

    @property
    def correct(self) -> bool:
        """Whether the attacker's best guess was right."""
        return self.truth_considered and self.truth_rank == 1


def attack(
    mechanism: HopMechanism,
    outputs: list[str],
    *,
    truth: str,
    independent: bool = True,
    candidate_radius: int | None = None,
) -> AttackResult:
    """Run the Bayesian attack and report how well it did, honestly."""
    belief = posterior_after(
        mechanism,
        outputs,
        independent=independent,
        candidate_radius=candidate_radius,
    )
    ranked = sorted(belief.items(), key=lambda item: item[1], reverse=True)
    canonical = normalise(truth)
    considered = canonical in belief

    rank = None
    probability = None
    if considered:
        rank = next(
            position
            for position, (name, _) in enumerate(ranked, start=1)
            if name == canonical
        )
        probability = belief[canonical]

    return AttackResult(
        outputs=tuple(outputs),
        candidates=len(belief),
        candidate_radius=candidate_radius,
        top_guess=ranked[0][0],
        top_probability=ranked[0][1],
        truth_considered=considered,
        truth_rank=rank,
        truth_probability=probability,
    )
