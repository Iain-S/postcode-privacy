"""Key handling at the command line.

The strictest rules in the CLI are here, because a leaked key makes every
perturbation in a release exactly invertible.
"""

from pathlib import Path

from click.testing import CliRunner

from postcode_privacy import Key
from postcode_privacy.cli import main


def test_keygen_writes_a_key_that_can_be_loaded(tmp_path: Path) -> None:
    out = tmp_path / "secret.key"

    result = CliRunner().invoke(main, ["keygen", "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert Key.from_file(out) is not None


def test_keygen_writes_the_key_readable_only_by_its_owner(tmp_path: Path) -> None:
    # A key sitting in a world-readable file on a shared analysis box is the
    # most likely way this gets lost, and chmod is easy to forget.
    out = tmp_path / "secret.key"

    CliRunner().invoke(main, ["keygen", "-o", str(out)])

    assert out.stat().st_mode & 0o077 == 0


def test_keygen_refuses_to_overwrite_an_existing_key(tmp_path: Path) -> None:
    # Overwriting a key silently orphans every release made with the old one:
    # those outputs can never be reproduced or explained again.
    out = tmp_path / "secret.key"
    out.write_bytes(b"existing")

    result = CliRunner().invoke(main, ["keygen", "-o", str(out)])

    assert result.exit_code != 0
    assert "exists" in result.output
    assert out.read_bytes() == b"existing"


def test_a_key_passed_on_the_command_line_is_refused_with_an_explanation(
    tmp_path: Path,
) -> None:
    # Click's default for an undefined option is "no such option", which teaches
    # the user nothing. The flag is defined precisely so it can refuse loudly:
    # a command line lands in shell history and in the process table.
    result = CliRunner().invoke(
        main, ["keygen", "--key", "hunter2", "-o", str(tmp_path / "k.key")]
    )

    assert result.exit_code != 0
    assert "shell history" in result.output


def test_the_refusal_does_not_echo_the_key_material(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main, ["keygen", "--key", "hunter2", "-o", str(tmp_path / "k.key")]
    )

    assert "hunter2" not in result.output
