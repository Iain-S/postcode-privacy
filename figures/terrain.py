"""Mosaic OS Terrain 50 into one coarse national elevation grid.

Terrain 50 ships as 2,859 ten-kilometre tiles, each its own zip inside one
outer zip, each holding an ASCII grid at fifty-metre resolution. A figure of
the whole country is a few thousand pixels wide, so the full resolution is
thrown away immediately; this reduces each tile on the way in and caches the
result, because re-reading 162 MB of nested archives per figure is wasteful.

OS Terrain 50 is Ordnance Survey data under the Open Government Licence, and is
used here only to shade the population density figure. It is not redistributed:
like every other input, it stays in the gitignored data directory.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np

SOURCE = Path("data/terrain50_ascii.zip")
CACHE = Path("data/terrain50_national.npz")

# Half a kilometre per cell. The national grid is 700 by 1,300 kilometres, so
# this is a 1,400 by 2,600 array -- ample for a figure and trivial to hold.
CELL_M = 500
NATIONAL_WIDTH_M = 700_000
NATIONAL_HEIGHT_M = 1_300_000
NODATA = -9999.0


def _read_tile(raw: bytes) -> tuple[dict[str, float], np.ndarray]:
    """Parse one ASCII grid into its header and its values."""
    lines = raw.decode("utf-8").splitlines()
    header: dict[str, float] = {}
    # Read while the line still looks like "key value". The number of header
    # lines varies: some tiles omit NODATA_value, and counting a fixed six
    # swallows a row of data.
    index = 0
    for index, line in enumerate(lines):  # noqa: B007
        parts = line.split()
        if len(parts) != 2 or not parts[0][0].isalpha():
            break
        header[parts[0].lower()] = float(parts[1])

    values = np.loadtxt(lines[index:], dtype=np.float32)
    return header, values


def build() -> np.ndarray:
    """Return the national grid, building and caching it on first use."""
    if CACHE.exists():
        return np.load(CACHE)["elevation"]
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"{SOURCE} not found. Download OS Terrain 50 (ASCII Grid) from the "
            "OS Downloads API; it is Open Government Licence."
        )

    columns = NATIONAL_WIDTH_M // CELL_M
    rows = NATIONAL_HEIGHT_M // CELL_M
    grid = np.full((rows, columns), np.nan, dtype=np.float32)

    with zipfile.ZipFile(SOURCE) as outer:
        inner_names = [n for n in outer.namelist() if n.endswith(".zip")]
        for index, name in enumerate(inner_names):
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                asc = next((m for m in inner.namelist() if m.endswith(".asc")), None)
                if asc is None:
                    continue
                header, values = _read_tile(inner.read(asc))

            values = np.where(values == NODATA, np.nan, values)
            factor = int(CELL_M // header["cellsize"])
            usable = (values.shape[0] // factor) * factor
            # Mean of each block, ignoring the sea cells marked as no-data.
            block = values[:usable, :usable].reshape(
                usable // factor, factor, usable // factor, factor
            )
            with np.errstate(invalid="ignore"):
                reduced = np.nanmean(block, axis=(1, 3))

            # ASCII grids run north to south; the national array is built the
            # same way, so the row offset is measured from the top.
            left = int(header["xllcorner"]) // CELL_M
            top = rows - int(header["yllcorner"]) // CELL_M - reduced.shape[0]
            patch = grid[top : top + reduced.shape[0], left : left + reduced.shape[1]]
            np.copyto(patch, reduced, where=~np.isnan(reduced))

            if index % 500 == 0:
                print(f"  {index:,}/{len(inner_names):,} tiles", flush=True)

    np.savez_compressed(CACHE, elevation=grid)
    return grid


if __name__ == "__main__":
    elevation = build()
    land = ~np.isnan(elevation)
    print(f"grid {elevation.shape}, land cells {land.sum():,} ({land.mean():.1%})")
    print(
        f"elevation min {np.nanmin(elevation):.0f} m max {np.nanmax(elevation):.0f} m"
    )
