"""What an attacker holding the key can and cannot conclude.

The documentation used to say that the key and the graph let an attacker
"invert every perturbation exactly". The first half is right -- they can
evaluate the mechanism and eliminate every postcode that does not produce the
observed output -- and the second half is not, because the keyed map is not
injective. These tests pin both halves, because overstating the consequence of
key compromise is as much a documentation defect as understating it.
"""

from __future__ import annotations

import numpy as np

from postcode_privacy import HopMechanism, Key, PostcodeGraph

N_NODES = 40
POSTCODES = [f"A{i:03d} 1AA" for i in range(N_NODES)]
SUBJECT = "subject-0001"


def a_graph() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array(POSTCODES),
        edges=np.array([[i, i + 1] for i in range(N_NODES - 1)], dtype=np.int64),
        prior=np.array([1 + (7 * i) % 5 for i in range(N_NODES)], dtype=np.int64),
        eastings=np.arange(N_NODES, dtype=np.int64) * 100,
        northings=np.zeros(N_NODES, dtype=np.int64),
    )


def the_whole_mapping() -> dict[str, str]:
    """Every true postcode's output for one subject, as the attacker computes it."""
    mechanism = HopMechanism(a_graph(), epsilon=1.0)
    key = Key.from_bytes(bytes(range(32)))
    return {
        postcode: mechanism.perturb(postcode, subject_id=SUBJECT, key=key)
        for postcode in POSTCODES
    }


def test_the_key_eliminates_almost_every_candidate() -> None:
    """The half of the old claim that was true, and it is the serious half.

    Every postcode outside the preimage of the observed output is ruled out with
    certainty rather than made unlikely. That is the whole guarantee gone, which
    is why the key has to be handled as the source data is.
    """
    mapping = the_whole_mapping()

    candidates = {
        output: [x for x, y in mapping.items() if y == output]
        for output in set(mapping.values())
    }

    assert max(len(c) for c in candidates.values()) < N_NODES / 4


def test_the_mapping_is_not_injective_so_inversion_is_not_unique() -> None:
    """The half that was overstated.

    Collisions are ordinary: the output depends on the true postcode only through
    a draw, and two draws can land in the same place. Any claim that compromise
    yields the true postcode uniquely is therefore wrong as a general statement,
    however little comfort the ambiguity offers in practice.
    """
    mapping = the_whole_mapping()

    assert len(set(mapping.values())) < len(mapping)
