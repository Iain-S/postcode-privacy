"""Utility measurement: what the mechanism costs an analyst."""

from pathlib import Path

import numpy as np
import pytest

from postcode_privacy import HopMechanism, PostcodeGraph
from postcode_privacy.evaluate.utility import (
    aligned_column,
    area_preservation,
    summarise_by_group,
)

N = 40


def line() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array([f"A{i:03d} 1AA" for i in range(N)]),
        edges=np.array([[i, i + 1] for i in range(N - 1)], dtype=np.int64),
        prior=np.ones(N, dtype=np.int64),
        eastings=np.arange(N, dtype=np.int64) * 500,
        northings=np.zeros(N, dtype=np.int64),
    )


def areas() -> np.ndarray:
    # Blocks of ten consecutive postcodes share an area.
    return np.array([f"E{i // 10:08d}" for i in range(N)])


def test_a_large_epsilon_keeps_almost_everyone_in_their_own_area() -> None:
    mechanism = HopMechanism(line(), epsilon=8.0)

    assert area_preservation(mechanism, "A015 1AA", areas()) > 0.95


def test_a_small_epsilon_scatters_people_out_of_their_area() -> None:
    # The utility cost, stated as the thing an analyst actually loses: the
    # ability to count people in a geography.
    strong = area_preservation(HopMechanism(line(), epsilon=8.0), "A015 1AA", areas())
    weak = area_preservation(HopMechanism(line(), epsilon=0.3), "A015 1AA", areas())

    assert weak < strong


def test_preservation_is_a_probability() -> None:
    value = area_preservation(HopMechanism(line(), epsilon=1.0), "A015 1AA", areas())

    assert 0.0 <= value <= 1.0


def test_results_are_grouped_so_a_national_average_cannot_hide_the_spread() -> None:
    # The whole design exists because protection and utility vary by place. A
    # single national figure would conceal exactly what matters.
    mechanism = HopMechanism(line(), epsilon=1.0)
    classes = np.array(["urban"] * 20 + ["rural"] * 20)

    grouped = summarise_by_group(
        mechanism,
        [f"A{i:03d} 1AA" for i in range(0, N, 4)],
        areas=areas(),
        groups=classes,
    )

    assert set(grouped) == {"urban", "rural"}
    for summary in grouped.values():
        assert summary.count > 0
        assert summary.median_km >= 0
        assert 0.0 <= summary.area_preserved <= 1.0


def test_a_column_can_be_aligned_to_the_graphs_node_order(tmp_path: Path) -> None:
    # ONSPD rows are not in the graph's order, and silently mismatching them
    # would attribute every measurement to the wrong postcode.
    source = tmp_path / "extra.csv"
    source.write_text(
        "pcds,lsoa21cd\n"
        '"A002 1AA","E01000003"\n'
        '"A000 1AA","E01000001"\n'
        '"A001 1AA","E01000002"\n'
    )

    column = aligned_column(
        source, np.array(["A000 1AA", "A001 1AA", "A002 1AA"]), "lsoa21cd"
    )

    assert list(column) == ["E01000001", "E01000002", "E01000003"]


def test_a_postcode_missing_from_the_source_is_marked_not_guessed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "extra.csv"
    source.write_text('pcds,lsoa21cd\n"A000 1AA","E01000001"\n')

    column = aligned_column(source, np.array(["A000 1AA", "A001 1AA"]), "lsoa21cd")

    assert column[0] == "E01000001"
    assert column[1] == ""


def test_an_absent_column_is_an_error_not_an_empty_result(tmp_path: Path) -> None:
    source = tmp_path / "extra.csv"
    source.write_text('pcds,lsoa21cd\n"A000 1AA","E01000001"\n')

    with pytest.raises(KeyError, match="nonexistent"):
        aligned_column(source, np.array(["A000 1AA"]), "nonexistent")


def test_several_columns_are_read_in_one_pass(tmp_path: Path) -> None:
    # The national file is over a gigabyte, so reading it once per column is
    # the dominant cost of an evaluation.
    from postcode_privacy.evaluate.utility import aligned_columns

    source = tmp_path / "extra.csv"
    source.write_text(
        "pcds,lsoa21cd,ruc21ind\n"
        '"A001 1AA","E01000002","A1"\n'
        '"A000 1AA","E01000001","B1"\n'
    )

    columns = aligned_columns(
        source, np.array(["A000 1AA", "A001 1AA"]), ["lsoa21cd", "ruc21ind"]
    )

    assert list(columns["lsoa21cd"]) == ["E01000001", "E01000002"]
    assert list(columns["ruc21ind"]) == ["B1", "A1"]
