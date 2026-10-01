"""The keyed pseudo-random function that drives the sampler.

All randomness in the library funnels through here. Everything downstream is a
deterministic function of the single integer this module produces, which is what
lets the rest of the test suite be exhaustive rather than statistical.
"""

import pytest

from postcode_privacy.mechanism.prf import Key, reduce_without_bias


def test_a_key_never_renders_its_material() -> None:
    # A key in a log line or a traceback is a key on disk somewhere unexpected.
    key = Key.from_bytes(b"\xde\xad\xbe\xef" * 8)

    assert "dead" not in repr(key).lower()
    assert "dead" not in str(key).lower()
    assert "dead" not in f"{key}".lower()
    assert "dead" not in "{}".format(key).lower()  # noqa: UP032


def test_a_key_does_not_leak_through_a_traceback() -> None:
    key = Key.from_bytes(b"\xde\xad\xbe\xef" * 8)

    with pytest.raises(ValueError) as excinfo:  # noqa: PT011
        raise ValueError(f"failed with {key!r}")

    assert "dead" not in str(excinfo.getrepr()).lower()


def test_generated_keys_differ() -> None:
    assert Key.generate().draw(b"x", bound=2**32) != Key.generate().draw(
        b"x", bound=2**32
    )


def test_a_key_must_be_long_enough_to_be_secret() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Key.from_bytes(b"short")


UINT64_MAX = 2**64 - 1


@pytest.mark.parametrize("bound", [3, 7, 10, 1_000_003, 2**40 + 1])
def test_the_final_incomplete_block_is_rejected(bound: int) -> None:
    # Values in the last partial block are what would make low residues more
    # likely than high ones, so they must be rejected rather than wrapped.
    usable = (2**64 // bound) * bound

    assert reduce_without_bias(usable - 1, bound) == (usable - 1) % bound
    assert reduce_without_bias(usable, bound) is None
    assert reduce_without_bias(UINT64_MAX, bound) is None


@pytest.mark.parametrize("bound", [1, 2, 256, 2**32])
def test_nothing_is_rejected_when_the_bound_divides_the_range(bound: int) -> None:
    assert reduce_without_bias(UINT64_MAX, bound) == UINT64_MAX % bound


def test_every_residue_is_reachable() -> None:
    # Exhaustive for a small bound: each residue has at least one preimage, so
    # no outcome is unreachable through the reduction.
    bound = 7
    reached = {reduce_without_bias(value, bound) for value in range(100)}
    assert reached == set(range(bound))


def test_the_draw_is_deterministic_in_its_inputs() -> None:
    key = Key.from_bytes(b"\x01" * 32)

    first = key.draw(b"patient-0041", b"LS2 9JT", bound=1_000_003)
    second = key.draw(b"patient-0041", b"LS2 9JT", bound=1_000_003)

    assert first == second


def test_a_different_key_gives_a_different_draw() -> None:
    fields = (b"patient-0041", b"LS2 9JT")

    a = Key.from_bytes(b"\x01" * 32).draw(*fields, bound=2**32)
    b = Key.from_bytes(b"\x02" * 32).draw(*fields, bound=2**32)

    assert a != b


def test_fields_are_separated_so_they_cannot_be_confused() -> None:
    # Without a separator, concatenation makes ("ab", "c") and ("a", "bc")
    # identical, so two different subjects could share a draw.
    key = Key.from_bytes(b"\x01" * 32)

    assert key.draw(b"ab", b"c", bound=2**32) != key.draw(b"a", b"bc", bound=2**32)


@pytest.mark.parametrize("bound", [1, 2, 5, 97])
def test_draws_respect_the_bound(bound: int) -> None:
    key = Key.from_bytes(b"\x01" * 32)

    for subject in range(50):
        assert 0 <= key.draw(str(subject).encode(), bound=bound) < bound
