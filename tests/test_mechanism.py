"""The public mechanism: postcodes in, postcodes out."""

import numpy as np
import pytest

from postcode_privacy import HopMechanism, Key, PostcodeGraph
from postcode_privacy.postcodes import (
    LargeUserPostcodeError,
    UnknownPostcodeError,
)

# A ring of six postcodes, so every node has the same local structure.
RING_EDGES = np.array([[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [0, 5]], dtype=np.int64)
RING_POSTCODES = ["AA1 1AA", "BB1 1BB", "CC1 1CC", "DD1 1DD", "EE1 1EE", "FF1 1FF"]


def ring() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array(RING_POSTCODES),
        edges=RING_EDGES,
        prior=np.ones(6, dtype=np.int64),
    )


def test_perturbing_returns_a_real_postcode_from_the_graph() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)

    output = mechanism.perturb("AA1 1AA", subject_id="p1", key=Key.generate())

    assert output in RING_POSTCODES


def test_the_same_subject_always_gets_the_same_output() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)
    key = Key.from_bytes(b"\x01" * 32)

    outputs = {
        mechanism.perturb("AA1 1AA", subject_id="p1", key=key) for _ in range(20)
    }

    assert len(outputs) == 1


def test_different_subjects_at_one_postcode_get_different_outputs() -> None:
    # Otherwise the mechanism would be a deterministic relabelling, which gives
    # no deniability at all.
    mechanism = HopMechanism(ring(), epsilon=0.2)
    key = Key.from_bytes(b"\x01" * 32)

    outputs = {
        mechanism.perturb("AA1 1AA", subject_id=f"p{i}", key=key) for i in range(60)
    }

    assert len(outputs) > 1


def test_input_postcodes_are_normalised() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)
    key = Key.from_bytes(b"\x01" * 32)

    assert mechanism.perturb("aa11aa", subject_id="p1", key=key) == mechanism.perturb(
        "AA1 1AA", subject_id="p1", key=key
    )


def test_an_unknown_postcode_is_rejected() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)

    with pytest.raises(UnknownPostcodeError, match="ZZ1 1ZZ"):
        mechanism.perturb("ZZ1 1ZZ", subject_id="p1", key=Key.generate())


def test_a_subject_identifier_is_required() -> None:
    # Without one the mechanism cannot keep a person's output consistent, and
    # repeated releases would spend epsilon over and over.
    mechanism = HopMechanism(ring(), epsilon=1.0)

    with pytest.raises(ValueError, match="subject"):
        mechanism.perturb("AA1 1AA", subject_id="", key=Key.generate())


def test_a_smaller_epsilon_needs_a_larger_radius() -> None:
    assert (
        HopMechanism(ring(), epsilon=0.5).radius
        > HopMechanism(ring(), epsilon=2.0).radius
    )


def test_the_chosen_radius_holds_teleport_probability_under_target() -> None:
    # A radius that is too small does not error -- it quietly sends outputs
    # anywhere in the country -- so the default must be derived, not guessed.
    mechanism = HopMechanism(ring(), epsilon=1.0, max_teleport=1e-9)

    for postcode in RING_POSTCODES:
        assert mechanism.distribution(postcode).teleport_probability <= 1e-9


def test_report_surfaces_the_chance_of_returning_the_true_postcode() -> None:
    # The general guard: whatever the cause, a self-probability near one means
    # the mechanism is handing back the secret.
    report = HopMechanism(ring(), epsilon=1.0).report("AA1 1AA")

    assert 0.0 < report.self_probability < 1.0
    assert report.postcode == "AA1 1AA"


def long_path(n: int = 200) -> PostcodeGraph:
    """A graph whose diameter exceeds any sensible radius.

    The ring above cannot test the radius at all: it is small enough that any
    radius reaches every node, so the tail is empty and the teleport probability
    is zero whatever the radius. Only a graph larger than the ball exercises the
    cap.
    """
    postcodes = np.array([f"A{i:03d} 1AA" for i in range(n)])
    edges = np.array([[i, i + 1] for i in range(n - 1)], dtype=np.int64)
    return PostcodeGraph.from_edges(
        postcodes=postcodes, edges=edges, prior=np.ones(n, dtype=np.int64)
    )


def test_each_postcode_gets_its_own_distribution() -> None:
    # The distribution cache is keyed by node. If it ever returned another
    # postcode's distribution, every output would be drawn around the wrong
    # place -- and nothing else here would notice.
    mechanism = HopMechanism(ring(), epsilon=1.0)

    sources = {
        postcode: mechanism.distribution(postcode).source for postcode in RING_POSTCODES
    }

    assert len(set(sources.values())) == len(RING_POSTCODES)
    for postcode in RING_POSTCODES:
        assert mechanism.report(postcode).postcode == postcode


def test_the_cache_survives_interleaved_lookups() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)

    first = mechanism.distribution("AA1 1AA").source
    mechanism.distribution("DD1 1DD")
    assert mechanism.distribution("AA1 1AA").source == first


@pytest.mark.parametrize("epsilon", [0.5, 1.0, 2.0])
def test_the_derived_radius_binds_on_a_graph_larger_than_the_ball(
    epsilon: float,
) -> None:
    graph = long_path()
    mechanism = HopMechanism(graph, epsilon=epsilon, max_teleport=1e-6)

    assert mechanism.radius < graph.n_nodes, "radius must actually bind here"
    for postcode in [graph.postcodes[0], graph.postcodes[100]]:
        assert mechanism.distribution(str(postcode)).teleport_probability <= 1e-6


def test_a_radius_smaller_than_the_derived_one_misses_the_target() -> None:
    # Pins the derivation itself rather than the inequality. Without this, a
    # radius formula that merely returned something large would pass.
    graph = long_path()
    derived = HopMechanism(graph, epsilon=1.0, max_teleport=1e-6).radius

    too_small = HopMechanism(graph, epsilon=1.0, radius=derived // 2)

    assert too_small.distribution(str(graph.postcodes[100])).teleport_probability > 1e-6


def ring_with_a_business_postcode() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array(RING_POSTCODES),
        edges=RING_EDGES,
        prior=np.ones(6, dtype=np.int64),
        excluded=np.array(["ZZ9 9ZZ"]),
    )


def test_a_large_user_postcode_is_rejected_with_an_explanation() -> None:
    # "Unknown postcode" would be true but useless: it is a real postcode, and
    # the caller needs to know why it cannot be used.
    mechanism = HopMechanism(ring_with_a_business_postcode(), epsilon=1.0)

    with pytest.raises(LargeUserPostcodeError) as excinfo:
        mechanism.perturb("ZZ9 9ZZ", subject_id="p1", key=Key.generate())

    message = str(excinfo.value)
    assert "ZZ9 9ZZ" in message
    assert "large user" in message.lower()
    assert "organisation" in message.lower()


def test_a_genuinely_unknown_postcode_still_reports_as_unknown() -> None:
    mechanism = HopMechanism(ring_with_a_business_postcode(), epsilon=1.0)

    with pytest.raises(UnknownPostcodeError):
        mechanism.perturb("YY8 8YY", subject_id="p1", key=Key.generate())


def test_no_output_is_ever_a_large_user_postcode() -> None:
    # The whole point: a business postcode has no residents to hide anyone
    # among, so it must never be emitted.
    mechanism = HopMechanism(ring_with_a_business_postcode(), epsilon=0.2)
    key = Key.from_bytes(b"\x03" * 32)

    outputs = {
        mechanism.perturb("AA1 1AA", subject_id=f"p{i}", key=key) for i in range(200)
    }

    assert outputs <= set(RING_POSTCODES)
