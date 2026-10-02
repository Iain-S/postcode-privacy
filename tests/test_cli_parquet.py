"""Parquet input and output, behind the [frames] extra."""

import json
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner, Result

from postcode_privacy.cli import main


def run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args)


@pytest.fixture
def parquet_records(tmp_path: Path) -> Path:
    path = tmp_path / "people.parquet"
    pd.DataFrame(
        {
            "patient_id": ["p1", "p2", "p3"],
            "postcode": ["AA1 1AA", "CC1 1CC", "AA1 1AA"],
            "age": [41, 62, 19],
        }
    ).to_parquet(path)
    return path


def args(source: Path, out: Path, artefact: Path, key_file: Path) -> list[str]:
    return [
        "perturb", str(source), "-o", str(out),
        "--graph", str(artefact), "--epsilon", "1.0",
        "--postcode-col", "postcode", "--subject-col", "patient_id",
        "--key-file", str(key_file),
    ]  # fmt: skip


def test_parquet_in_and_out(
    parquet_records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.parquet"

    result = run(args(parquet_records, out, artefact, key_file))

    assert result.exit_code == 0, result.output
    frame = pd.read_parquet(out)
    assert list(frame["patient_id"]) == ["p1", "p2", "p3"]
    assert frame["postcode_dp"].notna().all()
    # Types survive the round trip; a CSV detour would turn age into strings.
    assert frame["age"].tolist() == [41, 62, 19]


def test_parquet_in_csv_out(
    parquet_records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    # The formats are chosen per file, so a pipeline can change format and
    # perturb in one step.
    out = tmp_path / "out.csv"

    result = run(args(parquet_records, out, artefact, key_file))

    assert result.exit_code == 0, result.output
    assert "postcode_dp" in out.read_text()


def test_a_parquet_run_still_writes_a_manifest(
    parquet_records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.parquet"

    run(args(parquet_records, out, artefact, key_file))

    manifest = json.loads((tmp_path / "out.manifest.json").read_text())
    assert manifest["rows_in"] == 3
    assert manifest["rows_written"] == 3


def test_a_missing_column_is_reported_for_parquet_too(
    parquet_records: Path, artefact: Path, key_file: Path, tmp_path: Path
) -> None:
    bad = args(parquet_records, tmp_path / "o.parquet", artefact, key_file)
    bad[bad.index("--postcode-col") + 1] = "nonexistent"

    result = run(bad)

    assert result.exit_code != 0
    assert "nonexistent" in result.output
