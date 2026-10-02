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
HEADER = (
    "pcds,doterm,east1m,north1m,lad26cd,oa21cd,lsoa21cd,msoa21cd,ruc21ind,"
    "usrtypind,lat,long"
)


def _with_coords(row: str) -> str:
    """Append latitude and longitude consistent with the row's grid reference.

    Derived rather than written by hand, so a fixture cannot drift from the
    invariant the reader enforces: a grid reference must agree with its own
    coordinates. Fixtures encoding a wrong assumption is exactly the failure
    mode this repository watches for, and it is how the Irish Grid bug
    survived until a figure was drawn.
    """
    from pyproj import Transformer

    fields = row.split(",")
    easting, northing = fields[2].strip(), fields[3].strip()
    if not easting or not northing:
        return row + ",,"
    to_wgs84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    longitude, latitude = to_wgs84.transform(float(easting), float(northing))
    return f"{row},{latitude:.6f},{longitude:.6f}"


def write_onspd(path: Path, rows: list[str]) -> Path:
    """Write a miniature ONSPD file, defaulting rows to small-user."""
    # Two fewer commas than the header: lat and long are appended below.
    body = HEADER.count(",") - 2
    filled = [
        _with_coords(row if row.count(",") == body else row + ",0") for row in rows
    ]
    csv = path / "onspd.csv"
    csv.write_text("\n".join([HEADER, *filled]) + "\n")
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


@pytest.mark.parametrize(
    ("easting", "northing"),
    [
        ("0", "0"),  # the conventional "unknown location" sentinel
        ("-5", "433888"),
        ("429774", "0"),
        ("999999", "433888"),  # east of the national grid
        ("429774", "9999999"),  # north of the national grid
    ],
)
def test_coordinates_outside_the_national_grid_are_excluded(
    tmp_path: Path, easting: str, northing: str
) -> None:
    # A single stray point distorts the whole graph, not just its own row:
    # Delaunay triangulates the convex hull, so one absurd coordinate drags
    # enormous edges across the country. Real extremes are comfortably inside
    # the envelope -- Scilly, Shetland, Barra and Lowestoft all pass.
    csv = write_onspd(
        tmp_path,
        [
            "LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1",
            f"ZZ1 1ZZ,,{easting},{northing},E08000035,E00057834,E01011364,E02002393,A1",
        ],
    )

    table = read_onspd(csv)

    assert list(table.postcodes) == ["LS2 9JT"]
    assert table.dropped["outside_national_grid"] == 1


def test_large_user_postcodes_are_excluded_but_remembered(tmp_path: Path) -> None:
    # Large-user postcodes belong to a single organisation and have no resident
    # population, so they are never emitted. They are kept aside rather than
    # forgotten, so that a caller submitting one can be told what it is instead
    # of being told it does not exist.
    csv = write_onspd(
        tmp_path,
        [
            "LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1,0",
            "LS1 4AP,,429500,433500,E08000035,E00057835,E01011365,E02002394,A1,1",
        ],
    )

    table = read_onspd(csv)

    assert list(table.postcodes) == ["LS2 9JT"]
    assert list(table.large_user) == ["LS1 4AP"]
    assert table.dropped["large_user"] == 1


def test_output_area_codes_are_read(tmp_path: Path) -> None:
    # The population prior joins on these: output areas in England and Wales,
    # data zones in Northern Ireland, output areas in Scotland.
    csv = write_onspd(
        tmp_path,
        ["LS2 9JT,,429774,433888,E08000035,E00057834,E01011364,E02002393,A1,0"],
    )

    table = read_onspd(csv)

    assert list(table.output_areas) == ["E00057834"]


NI_ROW = (
    # Belfast. The grid reference is the IRISH Grid, as ONSPD supplies it; the
    # latitude and longitude are the authoritative position.
    "BT1 1DA,,333759,374365,0,N00000001,54.599803,-5.931046"
)
GB_ROW = "LS6 1AA,,428111,435817,0,E00057834,53.817875,-1.574508"


def write_with_coords(path: Path, rows: list[str]) -> Path:
    csv = path / "onspd_coords.csv"
    header = "pcds,doterm,east1m,north1m,usrtypind,oa21cd,lat,long"
    csv.write_text("\n".join([header, *rows]) + "\n")
    return csv


def test_northern_ireland_grid_references_are_reprojected(tmp_path: Path) -> None:
    # ONSPD gives Northern Ireland eastings and northings in the Irish Grid.
    # Read as British National Grid they put Belfast in Derbyshire, within the
    # valid envelope, so every range check passes and the graph is quietly
    # wrong. The authoritative latitude and longitude are used instead.
    table = read_onspd(write_with_coords(tmp_path, [NI_ROW]))

    assert list(table.postcodes) == ["BT1 1DA"]
    # Belfast in British National Grid, west of Scotland rather than in England.
    assert table.eastings[0] == pytest.approx(146_196, abs=200)
    assert table.northings[0] == pytest.approx(529_842, abs=200)


def test_great_britain_grid_references_are_used_as_supplied(tmp_path: Path) -> None:
    table = read_onspd(write_with_coords(tmp_path, [GB_ROW]))

    assert table.eastings[0] == 428_111
    assert table.northings[0] == 435_817


def test_a_grid_reference_that_contradicts_its_own_coordinates_is_refused(
    tmp_path: Path,
) -> None:
    # The check that would have caught the Northern Ireland bug on day one.
    # A grid reference far from where its latitude and longitude say it is
    # means the file's projection is not what we think it is.
    liar = "LS6 1AA,,100000,100000,0,E00057834,53.817875,-1.574508"

    with pytest.raises(OnspdSchemaError, match="grid reference"):
        read_onspd(write_with_coords(tmp_path, [liar]))
