"""Building the population prior.

The prior does not affect the guarantee -- it cancels in the likelihood ratio --
but it decides which postcode in a ring gets chosen, and so how many real people
an output could plausibly have come from. Measured on Scotland's per-postcode
figures, weighting by population roughly doubles the expected number of
residents at the output and removes the 6.5% of draws that would otherwise land
where nobody lives.

Resolution differs by nation: Scotland publishes population per postcode,
England and Wales per output area, Northern Ireland per data zone.
"""

from pathlib import Path

import numpy as np
import pytest

from postcode_privacy.graph.prior import PriorCoverage, population_prior


def write(path: Path, name: str, header: str, rows: list[str]) -> Path:
    file = path / name
    file.write_text("\n".join([header, *rows]) + "\n")
    return file


def test_an_area_population_is_split_across_its_postcodes(tmp_path: Path) -> None:
    postcodes = np.array(["AA1 1AA", "AA1 1AB", "BB1 1BB"])
    areas = np.array(["E00000001", "E00000001", "E00000002"])
    area_file = write(
        tmp_path,
        "areas.csv",
        "GEOGRAPHY_CODE,OBS_VALUE",
        ["E00000001,100", "E00000002,60"],
    )

    prior, _ = population_prior(postcodes, areas, area_populations=[area_file])

    # Two postcodes share the first area, one has the second to itself.
    assert prior.tolist() == [50, 50, 60]


def test_per_postcode_figures_take_precedence(tmp_path: Path) -> None:
    # Scotland publishes population per postcode, which is finer than the area
    # split and should win wherever it exists.
    postcodes = np.array(["AA1 1AA", "AA1 1AB"])
    areas = np.array(["S00000001", "S00000001"])
    area_file = write(
        tmp_path, "areas.csv", "GEOGRAPHY_CODE,OBS_VALUE", ["S00000001,100"]
    )
    postcode_file = write(
        tmp_path,
        "postcodes.csv",
        "Postcode,UsualResidentPopulation",
        ["AA1 1AA,80", "AA1 1AB,20"],
    )

    prior, _ = population_prior(
        postcodes,
        areas,
        area_populations=[area_file],
        postcode_populations=[postcode_file],
    )

    assert prior.tolist() == [80, 20]


def test_an_empty_postcode_is_floored_rather_than_removed(tmp_path: Path) -> None:
    # Census figures are rounded, suppressed and out of date: a new-build estate
    # reads as empty. Flooring keeps such a postcode usable while making it far
    # less likely to be chosen than an average one.
    postcodes = np.array(["AA1 1AA", "AA1 1AB"])
    areas = np.array(["S00000001", "S00000001"])
    postcode_file = write(
        tmp_path,
        "postcodes.csv",
        "Postcode,UsualResidentPopulation",
        ["AA1 1AA,40", "AA1 1AB,0"],
    )

    prior, _ = population_prior(postcodes, areas, postcode_populations=[postcode_file])

    assert prior.tolist() == [40, 1]


def test_every_prior_is_at_least_one(tmp_path: Path) -> None:
    # The mechanism requires it: a node that can never be produced cannot hide
    # anyone, and a zero weight would reintroduce an unreachable output.
    postcodes = np.array(["AA1 1AA", "ZZ9 9ZZ"])
    areas = np.array(["E00000001", "E00009999"])
    area_file = write(
        tmp_path, "areas.csv", "GEOGRAPHY_CODE,OBS_VALUE", ["E00000001,0"]
    )

    prior, _ = population_prior(postcodes, areas, area_populations=[area_file])

    assert (prior >= 1).all()


def test_coverage_is_reported_so_gaps_are_visible(tmp_path: Path) -> None:
    # Silently falling back to a floor across a whole nation would look exactly
    # like a working prior.
    postcodes = np.array(["AA1 1AA", "ZZ9 9ZZ"])
    areas = np.array(["E00000001", "E00009999"])
    area_file = write(
        tmp_path, "areas.csv", "GEOGRAPHY_CODE,OBS_VALUE", ["E00000001,40"]
    )

    _, coverage = population_prior(postcodes, areas, area_populations=[area_file])

    assert isinstance(coverage, PriorCoverage)
    assert coverage.from_area == 1
    assert coverage.from_postcode == 0
    assert coverage.unmatched == 1


def test_no_sources_at_all_is_refused() -> None:
    # A uniform prior is a legitimate choice, but it must be asked for, not
    # arrived at by supplying nothing.
    with pytest.raises(ValueError, match="no population"):
        population_prior(np.array(["AA1 1AA"]), np.array(["E00000001"]))


def test_split_postcodes_are_recombined(tmp_path: Path) -> None:
    # Where a postcode straddles a boundary, NRS publishes it as parts with a
    # trailing letter: "AB12 3GQA" and "AB12 3GQB". There are 252 such rows
    # holding 3,217 people. Dropping them would lose those residents and leave
    # the real postcode with no figure at all, so the parts are summed back.
    postcodes = np.array(["AB12 3GQ"])
    areas = np.array(["S00000001"])
    postcode_file = write(
        tmp_path,
        "postcodes.csv",
        "Postcode,UsualResidentPopulation",
        ["AB12 3GQA,5", "AB12 3GQB,7"],
    )

    prior, coverage = population_prior(
        postcodes, areas, postcode_populations=[postcode_file]
    )

    assert prior.tolist() == [12]
    assert coverage.from_postcode == 1
