"""Adversary simulations.

These exist so the library's claims are checkable rather than asserted. The
averaging attack in particular is the only thing that demonstrates keyed
determinism does any work: it must succeed against fresh randomness and fail
against the keyed mechanism.
"""

import numpy as np
import pytest

from postcode_privacy import HopMechanism, Key, PostcodeGraph
from postcode_privacy.evaluate.attack import averaging_attack, posterior

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


def test_averaging_many_independent_releases_recovers_the_truth() -> None:
    # The attack the keyed design exists to prevent. With fresh randomness per
    # release, the mean of enough outputs converges on the true location.
    mechanism = HopMechanism(line(), epsilon=0.5)

    result = averaging_attack(mechanism, "A030 1AA", releases=400, keyed=False, seed=0)

    assert result.error_km < 1.0


def test_the_keyed_mechanism_gives_the_attacker_nothing_extra() -> None:
    # The same subject always maps to the same output, so four hundred
    # observations are worth exactly one and averaging cannot help.
    mechanism = HopMechanism(line(), epsilon=0.5)
    key = Key.from_bytes(b"\x11" * 32)

    many = averaging_attack(
        mechanism, "A030 1AA", releases=400, keyed=True, key=key, seed=0
    )
    one = averaging_attack(
        mechanism, "A030 1AA", releases=1, keyed=True, key=key, seed=0
    )

    assert many.distinct_outputs == 1
    assert many.error_km == one.error_km


def test_the_attack_is_reproducible() -> None:
    # A privacy claim demonstrated by a number that changes between runs is
    # not a demonstration.
    mechanism = HopMechanism(line(), epsilon=0.5)

    first = averaging_attack(mechanism, "A030 1AA", releases=50, keyed=False, seed=7)
    second = averaging_attack(mechanism, "A030 1AA", releases=50, keyed=False, seed=7)

    assert first.error_km == second.error_km
