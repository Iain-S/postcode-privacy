"""Adversary simulations.

These exist so the library's claims are checkable rather than asserted. The
averaging attack in particular is the only thing that demonstrates keyed
determinism does any work: it must succeed against fresh randomness and fail
against the keyed mechanism.
"""

import numpy as np
import pytest

from postcode_privacy import HopMechanism, Key, PostcodeGraph
from postcode_privacy.evaluate.attack import (
    independent_releases,
    keyed_releases,
    posterior,
    posterior_after,
)

N = 60
SPACING_M = 500


def line() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array([f"A{i:03d} 1AA" for i in range(N)]),
        edges=np.array([[i, i + 1] for i in range(N - 1)], dtype=np.int64),
        prior=np.ones(N, dtype=np.int64),
        eastings=np.arange(N, dtype=np.int64) * SPACING_M,
        northings=np.zeros(N, dtype=np.int64),
    )


def test_the_posterior_concentrates_on_postcodes_near_the_output() -> None:
    # Sanity: an attacker seeing an output should believe the truth is nearby,
    # or the mechanism would be leaking nothing and also useless.
    mechanism = HopMechanism(line(), epsilon=1.0)

    belief = posterior(mechanism, "A030 1AA")

    best = max(belief, key=lambda candidate: belief[candidate])
    assert best == "A030 1AA"
    assert sum(belief.values()) == pytest.approx(1.0)


def test_a_larger_epsilon_gives_the_attacker_a_better_guess() -> None:
    # The direction that makes epsilon meaningful. If this were flat, the
    # parameter would not be buying anything.
    confidences = []
    for epsilon in (0.25, 1.0, 4.0):
        belief = posterior(HopMechanism(line(), epsilon=epsilon), "A030 1AA")
        confidences.append(max(belief.values()))

    assert confidences == sorted(confidences)


def test_more_independent_releases_make_the_attacker_more_confident() -> None:
    # The accumulation keyed determinism exists to prevent. Each fresh draw is
    # independent evidence about the same secret, so the posterior sharpens.
    mechanism = HopMechanism(line(), epsilon=0.5)

    confidences = []
    for count in (1, 5, 40):
        outputs = independent_releases(mechanism, "A030 1AA", count=count, seed=3)
        belief = posterior_after(mechanism, outputs)
        confidences.append(max(belief.values()))

    assert confidences == sorted(confidences)
    assert confidences[-1] > confidences[0]


def test_repeated_keyed_releases_add_nothing() -> None:
    # Every keyed release of one subject is the same value, so an attacker who
    # knows the scheme has one observation however many times it is published.
    # Forty must leave them exactly where one did.
    mechanism = HopMechanism(line(), epsilon=0.5)
    key = Key.from_bytes(b"\x11" * 32)
    once = keyed_releases(mechanism, "A030 1AA", count=1, key=key)
    many = keyed_releases(mechanism, "A030 1AA", count=40, key=key)

    assert set(many) == set(once)
    assert posterior_after(mechanism, many, independent=False) == posterior_after(
        mechanism, once, independent=False
    )


def test_releases_are_reproducible() -> None:
    # A privacy claim demonstrated by a number that changes between runs is
    # not a demonstration.
    mechanism = HopMechanism(line(), epsilon=0.5)

    first = independent_releases(mechanism, "A030 1AA", count=20, seed=7)
    second = independent_releases(mechanism, "A030 1AA", count=20, seed=7)

    assert first == second


def test_an_attacker_ignorant_of_the_scheme_overestimates_their_own_certainty() -> None:
    # Worth stating because it is a trap, not a safety margin. Treating forty
    # identical keyed releases as forty samples makes the attacker far more
    # confident than the evidence supports: they are wrong, not cautious. The
    # library is judged against the adversary who knows the scheme.
    mechanism = HopMechanism(line(), epsilon=0.5)
    key = Key.from_bytes(b"\x11" * 32)
    many = keyed_releases(mechanism, "A030 1AA", count=40, key=key)

    naive = max(posterior_after(mechanism, many, independent=True).values())
    informed = max(posterior_after(mechanism, many, independent=False).values())

    assert naive > informed
