"""Postcode normalisation.

Inputs arrive in every shape real data produces: lowercase, unspaced, and the
fixed-width form ONSPD uses internally, where the outward code is padded to four
characters. All must resolve to one canonical spelling, because node ordering --
and therefore keyed determinism -- depends on it.
"""

import pytest

from postcode_privacy.postcodes import InvalidPostcodeError, normalise


def test_normalise_uppercases_and_inserts_the_separating_space() -> None:
    assert normalise("ls29jt") == "LS2 9JT"


def test_normalise_collapses_the_fixed_width_padding_onspd_uses() -> None:
    # ONSPD's `pcd` column pads the outward code to four characters.
    assert normalise("M1  1AA") == "M1 1AA"


def test_normalise_is_idempotent() -> None:
    assert normalise(normalise("ls29jt")) == normalise("ls29jt")


@pytest.mark.parametrize("bad", ["", "ABC", "A", "LS29JTXXX"])
def test_normalise_rejects_strings_that_cannot_be_postcodes(bad: str) -> None:
    with pytest.raises(InvalidPostcodeError):
        normalise(bad)
