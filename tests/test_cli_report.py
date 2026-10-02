"""The report and calibrate commands."""

import json
from pathlib import Path

from click.testing import CliRunner, Result

from postcode_privacy.cli import main


def run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args)


def base(artefact: Path) -> list[str]:
    return ["report", "--graph", str(artefact), "--epsilon", "1.0"]


def test_report_on_one_postcode_gives_the_numbers_that_matter(
    artefact: Path,
) -> None:
    result = run([*base(artefact), "--postcode", "AA1 1AA"])

    assert result.exit_code == 0, result.output
    for expected in ["radius", "teleport", "self", "displacement"]:
        assert expected in result.output.lower()


def test_report_can_emit_json_for_a_pipeline(artefact: Path) -> None:
    result = run([*base(artefact), "--postcode", "AA1 1AA", "--json"])

    payload = json.loads(result.output)
    assert payload["postcode"] == "AA1 1AA"
    assert payload["epsilon"] == 1.0
    assert 0 <= payload["self_probability"] <= 1
    assert payload["median_km"] >= 0


def test_report_over_a_sample_summarises_the_country(artefact: Path) -> None:
    result = run([*base(artefact), "--sample", "4", "--json"])

    payload = json.loads(result.output)
    assert payload["sample_size"] == 4
    assert "median_km" in payload
    assert "p95_km" in payload


def test_report_needs_exactly_one_of_postcode_or_sample(artefact: Path) -> None:
    neither = run(base(artefact))
    both = run([*base(artefact), "--postcode", "AA1 1AA", "--sample", "4"])

    assert neither.exit_code != 0
    assert both.exit_code != 0
    assert "--postcode" in neither.output


def test_report_refuses_a_large_user_postcode_with_the_right_reason(
    artefact: Path,
) -> None:
    # The postcode is real, and saying "unknown" would send the user looking
    # for a typo that is not there.
    result = run([*base(artefact), "--postcode", "ZZ9 9ZZ"])

    assert result.exit_code != 0
    assert "large user" in result.output.lower()


def test_calibrate_solves_for_an_epsilon_and_shows_its_working(
    artefact: Path,
) -> None:
    result = run(
        ["calibrate", "--graph", str(artefact), "--target",
         "max-self-probability", "--value", "0.2", "--sample", "4"]
    )  # fmt: skip

    assert result.exit_code == 0, result.output
    assert "epsilon" in result.output.lower()
    assert "achieved" in result.output.lower()
    assert "sample" in result.output.lower()


def test_calibrate_lists_the_targets_when_given_a_bad_one(artefact: Path) -> None:
    result = run(
        ["calibrate", "--graph", str(artefact), "--target", "vibes", "--value", "1"]
    )

    assert result.exit_code != 0
    assert "median-displacement-km" in result.output


def test_calibrate_can_emit_json(artefact: Path) -> None:
    # Progress goes to stderr and the payload to stdout, so --json stays
    # machine-readable while a long solve still shows signs of life.
    result = run(
        ["calibrate", "--graph", str(artefact), "--target",
         "max-self-probability", "--value", "0.2", "--sample", "4", "--json"]
    )  # fmt: skip

    assert "solving: step" in result.stderr
    payload = json.loads(result.stdout)
    assert payload["target"] == "max-self-probability"
    assert payload["epsilon"] > 0
    assert payload["sample_size"] == 4
