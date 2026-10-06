"""The perturb command."""

import csv
import json
from pathlib import Path

from click.testing import CliRunner, Result

from postcode_privacy.cli import EXIT_ROWS_FAILED, main


def run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args)


def perturb_args(records: Path, out: Path, artefact: Path, key_file: Path) -> list[str]:
    return [
        "perturb", str(records), "-o", str(out),
        "--graph", str(artefact), "--epsilon", "1.0",
        "--postcode-col", "postcode", "--subject-col", "patient_id",
        "--key-file", str(key_file),
    ]  # fmt: skip


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_it_writes_a_perturbed_column_and_keeps_the_other_columns(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.csv"

    result = run(perturb_args(records, out, artefact, key_file))

    assert result.exit_code == 0, result.output
    rows = read(out)
    assert [row["patient_id"] for row in rows] == ["p1", "p2", "p3"]
    assert [row["age"] for row in rows] == ["41", "62", "19"]
    assert all(row["postcode_dp"] for row in rows)


def test_a_manifest_is_written_alongside_the_output(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # stderr gets lost; a file does not. The manifest is what makes a release
    # auditable and reproducible after the fact.
    out = tmp_path / "out.csv"

    run(perturb_args(records, out, artefact, key_file))

    manifest = json.loads((tmp_path / "out.manifest.json").read_text())
    assert manifest["epsilon"] == 1.0
    assert manifest["radius"] > 0
    assert manifest["rows_in"] == 3
    assert manifest["rows_written"] == 3
    assert manifest["distinct_postcodes"] == 2
    assert manifest["on_error"] == "error"
    assert manifest["graph"]["source"] == "ONSPD_TEST"
    assert manifest["graph"]["source_sha256"] == "a" * 64
    assert manifest["max_teleport_probability"] >= 0


def test_the_manifest_never_contains_key_material(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.csv"

    run(perturb_args(records, out, artefact, key_file))

    text = (tmp_path / "out.manifest.json").read_text()
    assert key_file.read_bytes().hex() not in text
    assert "key" not in text.lower() or "keyed" in text.lower()


def test_it_refuses_to_write_over_the_input(
    records: Path, artefact: Path, key_file: Path
) -> None:
    # The mechanism is not invertible without the key, so overwriting the source
    # destroys it for good.
    before = records.read_text()

    result = run(perturb_args(records, records, artefact, key_file))

    assert result.exit_code != 0
    assert "input" in result.output
    assert records.read_text() == before


def test_the_key_can_come_from_the_environment(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("POSTCODE_PRIVACY_KEY", key_file.read_bytes().hex())
    out = tmp_path / "out.csv"
    args = [
        a for a in perturb_args(records, out, artefact, key_file) if a != "--key-file"
    ]
    args.remove(str(key_file))

    result = run(args)

    assert result.exit_code == 0, result.output


def test_without_a_key_it_says_how_to_supply_one(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("POSTCODE_PRIVACY_KEY", raising=False)
    args = [
        a
        for a in perturb_args(records, tmp_path / "o.csv", artefact, key_file)
        if a != "--key-file"
    ]
    args.remove(str(key_file))

    result = run(args)

    assert result.exit_code != 0
    assert "--key-file" in result.output
    assert "POSTCODE_PRIVACY_KEY" in result.output


def test_a_bad_row_is_reported_by_number_and_never_by_postcode(
    artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # Naming the value would copy real postcodes out of the dataset and into
    # pipeline logs, which are usually less protected than the data itself.
    records = tmp_path / "bad.csv"
    records.write_text("patient_id,postcode\np1,AA1 1AA\np2,XX9 9XX\n")

    result = run(perturb_args(records, tmp_path / "out.csv", artefact, key_file))

    assert result.exit_code != 0
    assert "row 2" in result.output
    assert "XX9 9XX" not in result.output


def test_dropping_rows_exits_distinctly_and_records_the_count(
    artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    records = tmp_path / "bad.csv"
    records.write_text("patient_id,postcode\np1,AA1 1AA\np2,XX9 9XX\n")
    out = tmp_path / "out.csv"

    result = run(
        [*perturb_args(records, out, artefact, key_file), "--on-error", "drop"]
    )

    assert result.exit_code == EXIT_ROWS_FAILED
    assert [row["patient_id"] for row in read(out)] == ["p1"]
    manifest = json.loads((tmp_path / "out.manifest.json").read_text())
    assert manifest["rows_in"] == 2
    assert manifest["rows_written"] == 1
    assert manifest["rows_failed"] == 1


def test_the_privacy_parameters_are_printed(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # So they land in pipeline logs rather than being invisible.
    result = run(perturb_args(records, tmp_path / "out.csv", artefact, key_file))

    for expected in ["epsilon", "radius", "teleport", "ONSPD_TEST"]:
        assert expected in result.output


def test_the_true_postcode_is_not_in_the_output_by_default(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # The whole point of the release file. Copying the source column through
    # means the documented quickstart produces a file containing exactly the
    # values the mechanism exists to protect.
    out = tmp_path / "out.csv"

    result = run(perturb_args(records, out, artefact, key_file))

    assert result.exit_code == 0, result.output
    assert "postcode" not in read(out)[0]
    assert all(row["postcode_dp"] for row in read(out))
    # Unrelated columns are still carried.
    assert [row["age"] for row in read(out)] == ["41", "62", "19"]


def test_the_source_postcode_can_be_kept_but_only_on_purpose(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.csv"

    result = run(
        [*perturb_args(records, out, artefact, key_file), "--keep-source-postcode"]
    )

    assert result.exit_code == 0, result.output
    assert [row["postcode"] for row in read(out)] == ["AA1 1AA", "CC1 1CC", "AA1 1AA"]


def test_the_manifest_records_whether_the_source_was_kept(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # So a release can be audited after the fact rather than by opening it.
    out = tmp_path / "out.csv"

    run(perturb_args(records, out, artefact, key_file))
    assert (
        json.loads((tmp_path / "out.manifest.json").read_text())["source_postcode_kept"]
        is False
    )

    out2 = tmp_path / "out2.csv"
    run([*perturb_args(records, out2, artefact, key_file), "--keep-source-postcode"])
    assert (
        json.loads((tmp_path / "out2.manifest.json").read_text())[
            "source_postcode_kept"
        ]
        is True
    )


def test_an_out_col_colliding_with_an_existing_column_is_refused(
    records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # Silently overwriting `age` with postcodes would corrupt the release.
    args = [*perturb_args(records, tmp_path / "o.csv", artefact, key_file),
            "--out-col", "age"]  # fmt: skip

    result = run(args)

    assert result.exit_code != 0
    assert "age" in result.output


def test_a_blank_subject_id_in_a_csv_is_refused(
    artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # CSV's empty string and Parquet's null are the same logical thing and must
    # behave the same way.
    records = tmp_path / "blank.csv"
    records.write_text("patient_id,postcode\np1,AA1 1AA\n,AA1 1AA\n")

    result = run(perturb_args(records, tmp_path / "o.csv", artefact, key_file))

    assert result.exit_code != 0
    assert "subject" in result.output.lower()
    assert "row 2" in result.output
