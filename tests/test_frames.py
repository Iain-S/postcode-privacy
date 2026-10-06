"""Perturbing a dataframe column.

Behind the ``[frames]`` extra: pandas is optional for users of the library and
required only here.
"""

import numpy as np
import pandas as pd
import pytest

from postcode_privacy import HopMechanism, Key, PostcodeGraph
from postcode_privacy.postcodes import (
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


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "patient_id": ["p1", "p2", "p3"],
            "postcode": ["AA1 1AA", "CC1 1CC", "AA1 1AA"],
            "age": [41, 62, 19],
        }
    )


def perturbed(df: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
    mechanism = HopMechanism(ring(), epsilon=1.0)
    return mechanism.perturb_frame(
        df,
        postcode_col="postcode",
        subject_col="patient_id",
        key=Key.from_bytes(b"\x04" * 32),
        **kwargs,  # ty: ignore[invalid-argument-type]
    )


def test_the_output_column_is_added_and_the_input_is_left_alone() -> None:
    # The true postcode stays, because the caller decides when to drop it. What
    # must never happen is overwriting it in place, which would make the
    # original unrecoverable in a half-finished pipeline.
    result = perturbed(frame())

    assert list(result["postcode"]) == ["AA1 1AA", "CC1 1CC", "AA1 1AA"]
    assert "postcode_dp" in result.columns
    assert set(result["postcode_dp"]) <= set(RING_POSTCODES)


def test_the_default_output_column_name_cannot_be_mistaken_for_the_truth() -> None:
    # Named rather than incidental: an analyst who has not read the docs should
    # not be able to confuse a perturbed postcode for a real one.
    assert "postcode_dp" in perturbed(frame()).columns


def test_the_input_frame_is_not_modified() -> None:
    original = frame()

    perturbed(original)

    assert "postcode_dp" not in original.columns


def test_results_match_the_list_api() -> None:
    mechanism = HopMechanism(ring(), epsilon=1.0)
    key = Key.from_bytes(b"\x04" * 32)
    df = frame()

    result = mechanism.perturb_frame(
        df, postcode_col="postcode", subject_col="patient_id", key=key
    )

    assert list(result["postcode_dp"]) == mechanism.perturb_many(
        list(df["postcode"]), list(df["patient_id"]), key=key
    )


def test_unprocessable_rows_raise_by_default() -> None:
    df = frame()
    df.loc[1, "postcode"] = "XX9 9XX"

    with pytest.raises(UnknownPostcodeError):
        perturbed(df)


def test_drop_removes_the_row_entirely() -> None:
    df = frame()
    df.loc[1, "postcode"] = "XX9 9XX"

    result = perturbed(df, on_error="drop")

    assert list(result["patient_id"]) == ["p1", "p3"]


def test_null_keeps_the_row_with_no_output() -> None:
    df = frame()
    df.loc[1, "postcode"] = "XX9 9XX"

    result = perturbed(df, on_error="null")

    assert list(result["patient_id"]) == ["p1", "p2", "p3"]
    assert result["postcode_dp"].isna().tolist() == [False, True, False]


def test_a_missing_column_is_named_in_the_error() -> None:
    with pytest.raises(KeyError, match="nonexistent"):
        HopMechanism(ring(), epsilon=1.0).perturb_frame(
            frame(),
            postcode_col="nonexistent",
            subject_col="patient_id",
            key=Key.generate(),
        )


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA, "", "   "])
def test_a_missing_subject_id_is_refused_whatever_shape_it_takes(
    missing: object,
) -> None:
    # Converting to str() before checking turns None into "None" and NaN into
    # "nan", which are perfectly good non-empty identifiers. Two people with
    # missing ids at one postcode then share deterministic randomness and
    # receive the same output -- a silent privacy failure, not a type error.
    mechanism = HopMechanism(ring(), epsilon=1.0)
    df = pd.DataFrame(
        {
            "patient_id": ["p1", missing],
            "postcode": ["AA1 1AA", "AA1 1AA"],
        }
    )

    with pytest.raises(MissingSubjectIdError):
        mechanism.perturb_frame(
            df,
            postcode_col="postcode",
            subject_col="patient_id",
            key=Key.from_bytes(b"\x05" * 32),
        )


def test_two_missing_ids_do_not_quietly_share_an_output() -> None:
    # The consequence, stated directly: before the fix these produced the same
    # perturbed postcode, because both ids stringified to "nan".
    mechanism = HopMechanism(ring(), epsilon=1.0)
    df = pd.DataFrame(
        {
            "patient_id": [float("nan"), float("nan")],
            "postcode": ["AA1 1AA", "AA1 1AA"],
        }
    )

    with pytest.raises(MissingSubjectIdError):
        mechanism.perturb_frame(
            df,
            postcode_col="postcode",
            subject_col="patient_id",
            key=Key.from_bytes(b"\x05" * 32),
        )
