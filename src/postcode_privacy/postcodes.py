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


def is_missing(value: object) -> bool:
    """Whether a subject identifier is absent in any of the shapes it takes.

    Checked *before* any conversion to text. ``str(None)`` is ``"None"`` and
    ``str(float("nan"))`` is ``"nan"`` -- perfectly good non-empty identifiers
    as far as the keyed function is concerned. Two subjects with missing ids at
    the same postcode would then derive the same draw and receive the same
    output: a silent privacy failure rather than a loud type error.
    """
    if value is None:
        return True
    # NaN is the only value that is not equal to itself, which catches
    # float("nan") and numpy's float NaN without importing pandas here.
    if isinstance(value, float) and value != value:
        return True
    # pandas.NA and numpy.ma.masked are singletons whose truthiness raises.
    try:
        if bool(value) is False and not isinstance(value, int | float):
            return not str(value).strip()
    except (TypeError, ValueError):
        return True
    return not str(value).strip()


class MissingSubjectIdError(ValueError):
    """Raised when a record carries no stable subject identifier.

    Named rather than a bare ValueError because it has one specific remedy,
    and because the consequence of ignoring it is severe: without a stable
    identifier the same person cannot be given a consistent output, and
    every repeated release spends the privacy budget again.
    """


class LargeUserPostcodeError(KeyError):
    """Raised when a postcode exists but belongs to a single organisation.

    Distinct from "unknown" on purpose. The postcode is real, and the caller
    needs to know why it cannot be used rather than being told it does not
    exist.
    """

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


class UnknownPostcodeError(KeyError):
    """Raised when a postcode is well-formed but absent from the graph."""

    def __str__(self) -> str:
        # KeyError quotes its argument, which buries the message in repr noise.
        return str(self.args[0]) if self.args else ""


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
