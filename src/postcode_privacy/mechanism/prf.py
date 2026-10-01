"""Keyed randomness for the sampler.

Every random choice the library makes comes from here, as a single unbiased
integer. Isolating it this way is what lets the rest of the test suite enumerate
rather than sample: once the draw is a parameter, the mechanism is a pure
function of it.

The draw is also *deterministic* in the subject. The same person always receives
the same output, so releasing a dataset repeatedly leaks nothing further and the
privacy budget is spent once, however many times a pipeline runs.
"""

from __future__ import annotations

import hmac
import os
from hashlib import sha256
from pathlib import Path

# A key shorter than the hash's block security offers no benefit and invites
# someone to pass a passphrase instead.
KEY_BYTES = 32

# Separates the fields of the PRF input so that ("ab", "c") and ("a", "bc")
# cannot hash to the same value.
FIELD_SEPARATOR = b"\x00"

UINT64_RANGE = 2**64

# Extra bytes beyond the bound's own width, so that the rejected final block is
# a vanishing share of the range.
SLACK_BYTES = 8


class Key:
    """Secret key material that refuses to render itself.

    A key printed into a log line or a traceback is a key stored somewhere
    nobody is guarding, so ``repr`` and ``str`` are redacted. There is
    deliberately no constructor taking ``str``: passing a passphrase where key
    material is expected should be awkward.
    """

    __slots__ = ("_material",)

    def __init__(self, material: bytes) -> None:
        if len(material) < KEY_BYTES:
            raise ValueError(f"key material must be at least {KEY_BYTES} bytes")
        self._material = material

    @classmethod
    def from_bytes(cls, material: bytes) -> Key:
        return cls(material)

    @classmethod
    def generate(cls) -> Key:
        return cls(os.urandom(KEY_BYTES))

    @classmethod
    def from_file(cls, path: str | Path) -> Key:
        return cls(Path(path).read_bytes())

    @classmethod
    def from_env(cls, variable: str) -> Key:
        value = os.environ.get(variable)
        if not value:
            raise ValueError(f"environment variable {variable} is unset or empty")
        return cls(bytes.fromhex(value))

    def __repr__(self) -> str:
        return "<Key [redacted]>"

    __str__ = __repr__

    def draw(self, *fields: bytes, bound: int) -> int:
        """An unbiased integer in ``[0, bound)``, determined by ``fields``.

        The bound may be arbitrarily large. Shell weights are
        arbitrary-precision integers well beyond 64 bits, so the draw sizes
        itself to the bound rather than assuming a machine word; a fixed 64-bit
        draw would reject every value once the bound exceeded its range.
        """
        n_bytes = _bytes_needed(bound)
        value_range = 1 << (8 * n_bytes)
        message = FIELD_SEPARATOR.join(fields)

        for counter in range(_MAX_ATTEMPTS):
            value = int.from_bytes(
                _stream(self._material, message, counter, n_bytes), "big"
            )
            reduced = reduce_without_bias(value, bound, value_range=value_range)
            if reduced is not None:
                return reduced
        raise RuntimeError("PRF rejection sampling failed implausibly often")


# Rejection cannot plausibly recur this often: each attempt rejects with
# probability below 2**-32 for any bound we use.
_MAX_ATTEMPTS = 64


def _bytes_needed(bound: int) -> int:
    """Enough bytes that rejection is rare for a bound of this size."""
    if bound <= 0:
        raise ValueError("bound must be positive")
    # SLACK_BYTES of headroom keeps the rejected final block a vanishing share
    # of the range, so a draw almost never needs a second hash.
    return (bound - 1).bit_length() // 8 + 1 + SLACK_BYTES


def _stream(material: bytes, message: bytes, counter: int, n_bytes: int) -> bytes:
    """``n_bytes`` of keyed pseudo-random output, in counter mode."""
    blocks = []
    for block in range(-(-n_bytes // sha256().digest_size)):
        blocks.append(
            hmac.new(
                material,
                message
                + FIELD_SEPARATOR
                + counter.to_bytes(4, "big")
                + block.to_bytes(4, "big"),
                sha256,
            ).digest()
        )
    return b"".join(blocks)[:n_bytes]


def reduce_without_bias(
    value: int, bound: int, *, value_range: int = UINT64_RANGE
) -> int | None:
    """Map ``value`` from ``[0, value_range)`` into ``[0, bound)``, or reject.

    Taking ``value % bound`` directly would be biased whenever ``bound`` does not
    divide the range: the low residues would occur slightly more often than the
    high ones. Values in the final, incomplete block are rejected instead, which
    costs an occasional extra hash and buys exact uniformity.
    """
    if bound <= 0:
        raise ValueError("bound must be positive")
    usable = (value_range // bound) * bound
    if value >= usable:
        return None
    return value % bound
