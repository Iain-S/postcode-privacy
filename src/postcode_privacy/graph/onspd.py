"""Reading the ONS Postcode Directory into the arrays the graph build needs."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from pyproj import Transformer

from postcode_privacy.postcodes import normalise

# Northern Ireland postcodes all begin "BT".
NORTHERN_IRELAND_PREFIX = "BT"

# Column names as published in the August 2026 release. ONSPD renames columns
# between releases -- earlier ones called the grid reference oseast1m/osnrth1m --
# so the header is validated rather than assumed. Without that check a renamed
# column makes every row fail the grid-reference test, and an unreadable file
# looks exactly like an empty country.
POSTCODE_COLUMN = "pcds"
TERMINATION_COLUMN = "doterm"
EASTING_COLUMN = "east1m"
NORTHING_COLUMN = "north1m"
USER_TYPE_COLUMN = "usrtypind"
# Census small area. England and Wales use 2021 output areas, Scotland 2022
# output areas, Northern Ireland 2021 data zones; ONSPD puts all three here.
OUTPUT_AREA_COLUMN = "oa21cd"
LATITUDE_COLUMN = "lat"
LONGITUDE_COLUMN = "long"

# Royal Mail classes a postcode as "large user" when it belongs to a single
# organisation receiving a high volume of mail. Such a postcode has no
# resident population to hide anyone among, so it is never a valid output.
LARGE_USER = "1"

# The OSGB36 national grid. Real postcode extremes sit comfortably inside it:
# the Isles of Scilly, Shetland, Barra and Lowestoft are the four corners. A
# coordinate outside it is corrupt, and (0, 0) is the conventional sentinel for
# an unknown location. Either would distort the entire graph rather than just
# its own row, because Delaunay triangulates the convex hull and one absurd
# point drags enormous edges across the country.
MAX_EASTING = 700_000
MAX_NORTHING = 1_300_000

REQUIRED_COLUMNS = (
    POSTCODE_COLUMN,
    TERMINATION_COLUMN,
    EASTING_COLUMN,
    NORTHING_COLUMN,
    USER_TYPE_COLUMN,
    OUTPUT_AREA_COLUMN,
    LATITUDE_COLUMN,
    LONGITUDE_COLUMN,
)


# ONSPD supplies Northern Ireland eastings and northings in the IRISH Grid,
# not the British National Grid. Read as the latter they place Belfast in the
# Derbyshire Peak District -- inside the valid envelope, so every range check
# passes and the graph is quietly, badly wrong. The authoritative latitude and
# longitude are projected instead.
#
# Great Britain references are used as supplied, but checked against the same
# projection: a file whose grid no longer means what we think it means is
# refused rather than read. That check is what would have caught this on day one.
# The ONSPD User Guide requires these to be acknowledged or displayed wherever
# the data is used. They travel in the build manifest so that they reach anyone
# holding a derived artefact, rather than depending on a human remembering.
ATTRIBUTION = (
    "Contains OS data (c) Crown copyright and database right {year}",
    "Contains Royal Mail data (c) Royal Mail copyright and database right {year}",
    "Source: Office for National Statistics licensed under the Open Government "
    "Licence v.3.0",
)


def attribution(year: int) -> list[str]:
    """The attribution statements ONSPD requires, for a given data year."""
    return [line.format(year=year) for line in ATTRIBUTION]


WGS84 = "EPSG:4326"
BRITISH_NATIONAL_GRID = "EPSG:27700"
# Generous. The projection without a datum grid is accurate to a few metres and
# ONSPD centroids are rounded, but a wrong grid is wrong by hundreds of
# kilometres, so anything in between is still a loud failure.
MAX_GRID_DISCREPANCY_M = 1_000.0


class OnspdSchemaError(ValueError):
    """Raised when an ONSPD file lacks columns this reader needs."""


@dataclass(frozen=True)
class OnspdTable:
    """Live postcodes and the fields the build and evaluation stages use.

    Rows are ordered by normalised postcode. That ordering is canonical: node
    indices derive from it, and keyed determinism derives from node indices.
    """

    postcodes: npt.NDArray[np.str_]
    eastings: npt.NDArray[np.int64]
    northings: npt.NDArray[np.int64]
    output_areas: npt.NDArray[np.str_]
    large_user: npt.NDArray[np.str_]
    n_rows_read: int
    dropped: dict[str, int]


def read_onspd(path: Path, *, gb_only: bool = False) -> OnspdTable:
    """Read an ONSPD CSV extract, keeping only rows that can become nodes.

    Parameters
    ----------
    gb_only
        Exclude Northern Ireland postcodes. ONSPD's Northern Ireland records are
        licensed from Land & Property Services for internal use and may not be
        redistributed, so artefacts intended for sharing must be built this way.
    """
    pending: list[tuple[str, int, int, str, float, float]] = []
    large_user: list[str] = []
    dropped: dict[str, int] = {}
    n_rows_read = 0

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        _check_columns(reader.fieldnames, path)

        for row in reader:
            n_rows_read += 1
            postcode = normalise(row[POSTCODE_COLUMN])

            if row[TERMINATION_COLUMN].strip():
                drop("terminated")
                continue
            if gb_only and postcode.startswith(NORTHERN_IRELAND_PREFIX):
                drop("northern_ireland")
                continue
            if row[USER_TYPE_COLUMN].strip() == LARGE_USER:
                # Kept aside rather than forgotten, so a caller who submits one
                # can be told what it is instead of that it does not exist.
                large_user.append(postcode)
                drop("large_user")
                continue
            easting = row[EASTING_COLUMN].strip()
            northing = row[NORTHING_COLUMN].strip()
            latitude = row[LATITUDE_COLUMN].strip()
            longitude = row[LONGITUDE_COLUMN].strip()
            if not easting or not northing or not latitude or not longitude:
                drop("no_grid_reference")
                continue
            if not _on_the_national_grid(int(easting), int(northing)):
                drop("outside_national_grid")
                continue

            pending.append(
                (
                    postcode,
                    int(easting),
                    int(northing),
                    row[OUTPUT_AREA_COLUMN].strip(),
                    float(latitude),
                    float(longitude),
                )
            )

    rows = _resolve_coordinates(pending, path)
    rows.sort()
    columns = zip(*rows, strict=True) if rows else ((), (), (), ())
    postcodes, eastings, northings, output_areas = columns

    return OnspdTable(
        postcodes=np.array(postcodes, dtype=np.str_),
        eastings=np.array(eastings, dtype=np.int64),
        northings=np.array(northings, dtype=np.int64),
        output_areas=np.array(output_areas, dtype=np.str_),
        large_user=np.array(sorted(large_user), dtype=np.str_),
        n_rows_read=n_rows_read,
        dropped=dropped,
    )


def _resolve_coordinates(
    pending: list[tuple[str, int, int, str, float, float]], path: Path
) -> list[tuple[str, int, int, str]]:
    """Use the supplied grid references for GB, and projected ones for NI.

    Both are checked against the projection of the row's own latitude and
    longitude. Great Britain references must agree; Northern Ireland ones will
    not, because they are Irish Grid, and are replaced.
    """
    if not pending:
        return []

    latitudes = np.array([row[4] for row in pending])
    longitudes = np.array([row[5] for row in pending])
    transformer = Transformer.from_crs(WGS84, BRITISH_NATIONAL_GRID, always_xy=True)
    projected_e, projected_n = transformer.transform(longitudes, latitudes)

    supplied_e = np.array([row[1] for row in pending], dtype=np.float64)
    supplied_n = np.array([row[2] for row in pending], dtype=np.float64)
    discrepancy = np.hypot(projected_e - supplied_e, projected_n - supplied_n)

    northern_ireland = np.array(
        [row[0].startswith(NORTHERN_IRELAND_PREFIX) for row in pending]
    )
    disagrees = discrepancy > MAX_GRID_DISCREPANCY_M
    unexplained = disagrees & ~northern_ireland
    if unexplained.any():
        worst = int(np.argmax(np.where(unexplained, discrepancy, 0)))
        raise OnspdSchemaError(
            f"{path} has {int(unexplained.sum()):,} rows whose grid reference "
            f"contradicts their own latitude and longitude, the worst by "
            f"{discrepancy[worst]:,.0f} m ({pending[worst][0]}). The file's "
            "projection is not the British National Grid this reader assumes."
        )

    eastings = np.where(northern_ireland, projected_e, supplied_e)
    northings = np.where(northern_ireland, projected_n, supplied_n)
    return [
        (row[0], round(east), round(north), row[3])
        for row, east, north in zip(pending, eastings, northings, strict=True)
    ]


def _check_columns(fieldnames: Sequence[str] | None, path: Path) -> None:
    """Fail loudly when the file does not carry the columns we read."""
    present = set(fieldnames or ())
    missing = [column for column in REQUIRED_COLUMNS if column not in present]
    if missing:
        raise OnspdSchemaError(
            f"{path} is missing required ONSPD column(s): {', '.join(missing)}. "
            "Column names differ between ONSPD releases; this reader expects the "
            "August 2026 naming."
        )


def _on_the_national_grid(easting: int, northing: int) -> bool:
    """Whether a grid reference could plausibly be a UK location."""
    return 0 < easting < MAX_EASTING and 0 < northing < MAX_NORTHING
