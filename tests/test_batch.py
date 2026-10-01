"""Batch perturbation of many records at once."""

import numpy as np
import pytest

from postcode_privacy import HopMechanism, Key, PostcodeGraph
from postcode_privacy.postcodes import (
    LargeUserPostcodeError,
    MissingSubjectIdError,
    UnknownPostcodeError,
)

RING_POSTCODES = ["AA1 1AA", "BB1 1BB", "CC1 1CC", "DD1 1DD", "EE1 1EE", "FF1 1FF"]
RING_EDGES = np.array([[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [0, 5]], dtype=np.int64)


def ring() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array(RING_POSTCODES),
        edges=RING_EDGES,
        prior=np.ones(6, dtype=np.int64),
    )


def test_a_missing_subject_id_raises_a_named_error() -> None:
    # A bare ValueError is indistinguishable from any other bad argument, and
    # this one has a specific remedy: supply a stable identifier.
    mechanism = HopMechanism(ring(), epsilon=1.0)

    with pytest.raises(MissingSubjectIdError):
        mechanism.perturb("AA1 1AA", subject_id="", key=Key.generate())


def test_batch_results_match_perturbing_one_at_a_time() -> None:
    # The batch path exists for speed, not for different behaviour. If it ever
    # disagreed with perturb(), the goldens would protect only one of them.
    mechanism = HopMechanism(ring(), epsilon=1.0)
    key = Key.from_bytes(b"\x02" * 32)
    postcodes = ["AA1 1AA", "CC1 1CC", "AA1 1AA", "FF1 1FF"]
    subjects = ["p1", "p2", "p3", "p4"]

    batch = mechanism.perturb_many(postcodes, subjects, key=key)

    assert batch == [
        mechanism.perturb(p, subject_id=s, key=key)
        for p, s in zip(postcodes, subjects, strict=True)
    ]


def test_each_distinct_postcode_is_expanded_only_once() -> None:
    # The whole point of the batch path: a dataset holds far fewer distinct
    # postcodes than rows, and expanding the ball is the expensive part.
    mechanism = HopMechanism(ring(), epsilon=1.0)
    key = Key.from_bytes(b"\x02" * 32)
    postcodes = ["AA1 1AA"] * 50 + ["CC1 1CC"] * 50
    subjects = [f"p{i}" for i in range(100)]

    mechanism.perturb_many(postcodes, subjects, key=key)

    assert len(mechanism._cache) == 2


def test_mismatched_input_lengths_are_rejected() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)

    with pytest.raises(ValueError, match="same length"):
        mechanism.perturb_many(["AA1 1AA"], ["p1", "p2"], key=Key.generate())


def ring_with_a_business_postcode() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array(RING_POSTCODES),
        edges=RING_EDGES,
        prior=np.ones(6, dtype=np.int64),
        excluded=np.array(["ZZ9 9ZZ"]),
    )


def test_an_unprocessable_row_raises_by_default() -> None:
    # Defaulting to error is deliberate: a dataset quietly losing rows is a
    # worse outcome than a run that stops and says why.
    mechanism = HopMechanism(ring(), epsilon=1.0)

    with pytest.raises(UnknownPostcodeError):
        mechanism.perturb_many(["AA1 1AA", "XX9 9XX"], ["p1", "p2"], key=Key.generate())


@pytest.mark.parametrize(
    ("postcode", "expected_error"),
    [("XX9 9XX", UnknownPostcodeError), ("ZZ9 9ZZ", LargeUserPostcodeError)],
)
def test_on_error_null_substitutes_none_and_keeps_alignment(
    postcode: str, expected_error: type[Exception]
) -> None:
    mechanism = HopMechanism(ring_with_a_business_postcode(), epsilon=1.0)
    key = Key.from_bytes(b"\x03" * 32)

    with pytest.raises(expected_error):
        mechanism.perturb_many(["AA1 1AA", postcode], ["p1", "p2"], key=key)

    results = mechanism.perturb_many(
        ["AA1 1AA", postcode], ["p1", "p2"], key=key, on_error="null"
    )

    assert results[0] is not None
    assert results[1] is None


def test_drop_is_refused_for_the_list_api() -> None:
    # Dropping rows from a list result would silently break the correspondence
    # between input row and output row, which is a worse failure than refusing.
    mechanism = HopMechanism(ring(), epsilon=1.0)

    with pytest.raises(ValueError, match="alignment"):
        mechanism.perturb_many(["AA1 1AA"], ["p1"], key=Key.generate(), on_error="drop")


def test_an_unrecognised_policy_is_refused() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)

    with pytest.raises(ValueError, match="on_error"):
        mechanism.perturb_many(
            ["AA1 1AA"], ["p1"], key=Key.generate(), on_error="ignore"
        )
