"""The evaluate command."""

import json
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner, Result

from postcode_privacy import PostcodeGraph, Provenance, save_graph
from postcode_privacy.cli import main


@pytest.fixture
def bigger_artefact(tmp_path: Path) -> Path:
    """A graph with enough nodes to sample groups from."""
    n = 24
    graph = PostcodeGraph.from_edges(
        postcodes=np.array([f"A{i:03d} 1AA" for i in range(n)]),
        edges=np.array([[i, i + 1] for i in range(n - 1)], dtype=np.int64),
        prior=np.ones(n, dtype=np.int64),
        eastings=np.arange(n, dtype=np.int64) * 500,
        northings=np.zeros(n, dtype=np.int64),
    )
    path = tmp_path / "big.ppg"
    save_graph(
        graph,
        path,
        provenance=Provenance(
            source="ONSPD_TEST",
            source_sha256="b" * 64,
            gb_only=True,
            max_edge_km=None,
            prune_alpha=None,
            library_version="0.0.0",
        ),
    )
    return path


@pytest.fixture
def extra_columns(tmp_path: Path) -> Path:
    path = tmp_path / "extra.csv"
    rows = [
        f'"A{i:03d} 1AA","E{i // 6:08d}","{"UN1" if i < 12 else "RSN1"}","E92000001"'
        for i in range(24)
    ]
    path.write_text("pcds,lsoa21cd,ruc21ind,ctry26cd\n" + "\n".join(rows) + "\n")
    return path


def run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args)


def evaluate_args(artefact: Path, extra: Path) -> list[str]:
    return [
        "evaluate", "--graph", str(artefact), "--onspd", str(extra),
        "--epsilon", "1.0", "--per-group", "3",
    ]  # fmt: skip


def test_it_reports_each_group_separately(
    bigger_artefact: Path, extra_columns: Path
) -> None:
    result = run(evaluate_args(bigger_artefact, extra_columns))

    assert result.exit_code == 0, result.output
    assert "urban" in result.output
    assert "rural" in result.output


def test_json_output_carries_the_numbers_and_their_provenance(
    bigger_artefact: Path, extra_columns: Path
) -> None:
    # Numbers quoted in documentation have to be traceable to the graph that
    # produced them, or they are just assertions with decimal points.
    result = run([*evaluate_args(bigger_artefact, extra_columns), "--json"])

    payload = json.loads(result.stdout)
    assert payload["epsilon"] == 1.0
    assert payload["graph"]["source"] == "ONSPD_TEST"
    assert payload["seed"] == 0
    for group in payload["groups"].values():
        assert group["count"] > 0
        assert 0.0 <= group["area_preserved"] <= 1.0


def test_it_says_when_a_group_was_too_small_to_sample(
    bigger_artefact: Path, extra_columns: Path
) -> None:
    # Silently sampling fewer than asked would make two runs incomparable
    # without anything saying why.
    result = run([*evaluate_args(bigger_artefact, extra_columns), "--per-group", "50"])

    assert result.exit_code == 0, result.output
    assert "requested 50" in result.output.lower()
