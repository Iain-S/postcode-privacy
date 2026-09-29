"""Reading the ONS Postcode Directory into the arrays the graph build needs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from postcode_privacy.postcodes import normalise

# Northern Ireland postcodes all begin "BT".
NORTHERN_IRELAND_PREFIX = "BT"


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
        for row in csv.DictReader(handle):
            n_rows_read += 1
            postcode = normalise(row["pcds"])

            if row["doterm"].strip():
                drop("terminated")
                continue
            if gb_only and postcode.startswith(NORTHERN_IRELAND_PREFIX):
                drop("northern_ireland")
                continue
            easting, northing = row["oseast1m"].strip(), row["osnrth1m"].strip()
            if not easting or not northing:
                drop("no_grid_reference")
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
