"""Reading the ONS Postcode Directory into the arrays the graph build needs."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

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
)


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
    rows: list[tuple[str, int, int]] = []
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
            easting = row[EASTING_COLUMN].strip()
            northing = row[NORTHING_COLUMN].strip()
            if not easting or not northing:
                drop("no_grid_reference")
                continue
            if not _on_the_national_grid(int(easting), int(northing)):
                drop("outside_national_grid")
                continue

            rows.append((postcode, int(easting), int(northing)))

    rows.sort()
    postcodes, eastings, northings = zip(*rows, strict=True) if rows else ((), (), ())

    return OnspdTable(
        postcodes=np.array(postcodes, dtype=np.str_),
        eastings=np.array(eastings, dtype=np.int64),
        northings=np.array(northings, dtype=np.int64),
        n_rows_read=n_rows_read,
        dropped=dropped,
    )


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
