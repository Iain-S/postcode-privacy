"""Canonical spelling of UK postcodes.

Node ordering in a graph artefact is by normalised postcode, and keyed
determinism depends on that ordering, so normalisation is part of the privacy
contract rather than a convenience.
"""

# A UK postcode is five to seven characters once whitespace is removed: an
# outward code of two to four, and an inward code of always exactly three.
MIN_COMPACT_LENGTH = 5
MAX_COMPACT_LENGTH = 7


class InvalidPostcodeError(ValueError):
    """Raised when a string cannot be a UK postcode."""


def normalise(postcode: str) -> str:
    """Return ``postcode`` in canonical form: upper case, one separating space.

    The inward code of a UK postcode is always exactly three characters, so the
    separator position is determined by the end of the string rather than by
    whatever spacing the input happened to use.
    """
    compact = "".join(postcode.split()).upper()
    if not MIN_COMPACT_LENGTH <= len(compact) <= MAX_COMPACT_LENGTH:
        raise InvalidPostcodeError(f"not a UK postcode: {postcode!r}")
    return f"{compact[:-3]} {compact[-3:]}"
