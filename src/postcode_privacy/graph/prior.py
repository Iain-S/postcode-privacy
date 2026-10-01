"""Building the population prior.

The prior does not affect the guarantee: it cancels in the likelihood ratio, so
any strictly positive weighting satisfies epsilon-d-privacy. What it decides is
which postcode within a ring is chosen, since every postcode at the same hop
distance carries the same exponential factor and the prior is the only thing
separating them.

That matters because the mechanism hides a person among postcodes, while what
protects them is being hidden among *people*. Measured on Scotland's
per-postcode census figures, weighting by population roughly doubles the
expected number of residents at the output -- 35.5 to 71.2 -- and removes the
6.5% of draws that would otherwise land on a postcode where nobody lives. Such
an output still satisfies the bound, but it offers no cover in practice: anyone
with local knowledge discards it immediately.

The United Kingdom has no single census, so resolution differs by nation.
Scotland publishes population per postcode, England and Wales per 2021 output
area, and Northern Ireland per 2021 data zone. Per-postcode figures are used
where they exist; otherwise an area's population is divided evenly among its
postcodes, which captures variation between areas but not within them.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from postcode_privacy.postcodes import normalise

# Census counts are rounded, suppressed and inevitably out of date -- a
# new-build estate reads as empty. A floor keeps such a postcode usable as both
# input and output while making it far less likely to be chosen than an average
# one. It is also what the mechanism requires: a zero weight would make a node
# unreachable, and a node that can never be produced can hide nobody.
MINIMUM_PRIOR = 1


@dataclass(frozen=True)
class PriorCoverage:
    """Where each postcode's weight came from.

    Reported rather than returned quietly: falling back to the floor across a
    whole nation would otherwise look exactly like a working prior.
    """

    from_postcode: int
    from_area: int
    unmatched: int

    @property
    def total(self) -> int:
        return self.from_postcode + self.from_area + self.unmatched


def population_prior(
    postcodes: npt.NDArray[np.str_],
    output_areas: npt.NDArray[np.str_],
    *,
    area_populations: list[Path] | None = None,
    postcode_populations: list[Path] | None = None,
) -> tuple[npt.NDArray[np.int64], PriorCoverage]:
    """Residential population weight per postcode, aligned with ``postcodes``."""
    if not area_populations and not postcode_populations:
        raise ValueError(
            "no population sources given; pass census files, or ask for a "
            "uniform prior explicitly"
        )

    by_postcode = _read_pairs(postcode_populations or [], key=normalise)
    by_area = _read_pairs(area_populations or [], key=str)
    postcodes_per_area = Counter(output_areas.tolist())

    weights = np.empty(len(postcodes), dtype=np.int64)
    from_postcode = from_area = unmatched = 0

    for index, (postcode, area) in enumerate(
        zip(postcodes.tolist(), output_areas.tolist(), strict=True)
    ):
        if postcode in by_postcode:
            weights[index] = by_postcode[postcode]
            from_postcode += 1
        elif area in by_area:
            # Even division captures differences between areas but not within
            # them, so this is coarser than a per-postcode figure.
            weights[index] = by_area[area] // postcodes_per_area[area]
            from_area += 1
        else:
            weights[index] = 0
            unmatched += 1

    np.maximum(weights, MINIMUM_PRIOR, out=weights)
    return weights, PriorCoverage(from_postcode, from_area, unmatched)


def _read_pairs(paths: list[Path], *, key: Callable[[str], str]) -> dict[str, int]:
    """Read ``code,population`` CSVs into one lookup, by first two columns."""
    lookup: dict[str, int] = {}
    for path in paths:
        with Path(path).open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            next(reader, None)  # header
            for row in reader:
                if len(row) < 2 or not row[1].strip():
                    continue
                name = row[0].strip()
                lookup[key(name)] = int(row[1])
    return lookup
