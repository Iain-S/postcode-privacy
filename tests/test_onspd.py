"""Reading the ONS Postcode Directory.

Fixtures here are miniature ONSPD files rather than real extracts: no postcode
data belongs in this repository, and Northern Ireland records in particular are
not redistributable.
"""

from pathlib import Path

import pytest

from postcode_privacy.graph.onspd import OnspdSchemaError, read_onspd

# These are the real ONSPD column names, verified against the August 2026
# release. Earlier releases used oseast1m/osnrth1m and the fixture encoded
# that guess, so the suite passed while the reader could not read a real file.
HEADER = "pcds,doterm,east1m,north1m,lad26cd,oa21cd,lsoa21cd,msoa21cd,ruc21ind"


def write_onspd(path: Path, rows: list[str]) -> Path:
    csv = path / "onspd.csv"
    csv.write_text("\n".join([HEADER, *rows]) + "\n")
    return csv


def test_reads_live_postcodes_with_their_grid_references(tmp_path: Path) -> None:
    csv = write_onspd(
        tmp_path,
        ["LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1"],
    )

    table = read_onspd(csv)

    assert list(table.postcodes) == ["LS2 9JT"]
    assert list(table.eastings) == [429774]
    assert list(table.northings) == [433888]


def test_terminated_postcodes_are_excluded(tmp_path: Path) -> None:
    # Emitting a postcode that no longer exists would be an obvious tell that
    # the value is synthetic, so terminated records never become nodes.
    csv = write_onspd(
        tmp_path,
        [
            "LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1",
            "LS1 1AA,201907,429000,433000,E08000035,E00057800,E01011300,E02002300,A1",
        ],
    )

    table = read_onspd(csv)

    assert list(table.postcodes) == ["LS2 9JT"]


def test_records_without_a_grid_reference_are_excluded(tmp_path: Path) -> None:
    # A postcode with no coordinates cannot be placed in the triangulation.
    csv = write_onspd(
        tmp_path,
        [
            "LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1",
            "GY1 1AA,,,,L99999999,,,,",
        ],
    )

    table = read_onspd(csv)

    assert list(table.postcodes) == ["LS2 9JT"]


def test_rows_are_ordered_canonically_by_postcode(tmp_path: Path) -> None:
    # Node indices derive from this ordering and keyed determinism derives from
    # node indices, so input order must not leak into the artefact.
    csv = write_onspd(
        tmp_path,
        [
            "LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1",
            "AB1 0AA,,385000,801000,S12000033,S00090000,S01006500,S02001200,1",
            "M1 1AA,,384000,398000,E08000003,E00056000,E01005000,E02001000,A1",
        ],
    )

    table = read_onspd(csv)

    assert list(table.postcodes) == ["AB1 0AA", "LS2 9JT", "M1 1AA"]
    assert list(table.eastings) == [385000, 429774, 384000]


def test_gb_only_excludes_northern_ireland(tmp_path: Path) -> None:
    # ONSPD's Northern Ireland records carry a Land & Property Services end-user
    # licence and are not redistributable, so a build intended for sharing must
    # be able to leave them out.
    csv = write_onspd(
        tmp_path,
        [
            "LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1",
            "BT1 1AA,,333000,374000,N09000003,N00000001,N01000001,N02000001,A",
        ],
    )

    assert list(read_onspd(csv).postcodes) == ["BT1 1AA", "LS2 9JT"]
    assert list(read_onspd(csv, gb_only=True).postcodes) == ["LS2 9JT"]


def test_dropped_rows_are_counted_by_reason(tmp_path: Path) -> None:
    # Dropping rows silently would let a chunk of the country vanish from a
    # release without anyone noticing, so the reasons are always reported.
    csv = write_onspd(
        tmp_path,
        [
            "LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1",
            "LS1 1AA,201907,429000,433000,E08000035,E00057800,E01011300,E02002300,A1",
            "GY1 1AA,,,,L99999999,,,,",
            "BT1 1AA,,333000,374000,N09000003,N00000001,N01000001,N02000001,A",
        ],
    )

    table = read_onspd(csv, gb_only=True)

    assert table.dropped == {
        "terminated": 1,
        "no_grid_reference": 1,
        "northern_ireland": 1,
    }
    assert table.n_rows_read == 4


def test_grid_references_may_be_zero_padded(tmp_path: Path) -> None:
    # Northings in the real file are written with a leading zero, e.g. "0801193".
    csv = write_onspd(
        tmp_path,
        ["AB10 1AL,,385386,0801193,S12000033,S00137176,S01006506,S02001261,1"],
    )

    table = read_onspd(csv)

    assert list(table.northings) == [801193]


def test_a_file_missing_required_columns_is_rejected(tmp_path: Path) -> None:
    # ONSPD renames columns between releases. Without this check the reader
    # silently drops every row, which looks like an empty country rather than an
    # unreadable file.
    csv = tmp_path / "old.csv"
    csv.write_text("pcds,doterm,oseast1m,osnrth1m\nLS2 9JT,,429774,433888\n")

    with pytest.raises(OnspdSchemaError) as excinfo:
        read_onspd(csv)

    assert "east1m" in str(excinfo.value)
    assert "north1m" in str(excinfo.value)
