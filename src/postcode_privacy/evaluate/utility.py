"""What the mechanism costs an analyst.

Every figure here is reported by group rather than as a national average. That
is not presentation: the whole reason this library measures privacy in hops is
that protection and utility vary enormously by place, and a single national
number would conceal exactly the disparity the design exists to address.

Area codes are read from ONSPD rather than carried in the artefact. Evaluation
is a research activity performed where the source data already lives, and
adding twenty megabytes to every artefact to serve it would be the same bad
trade as carrying the terminated postcodes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from postcode_privacy.mechanism.calibrate import displacement_summary
from postcode_privacy.mechanism.mechanism import HopMechanism
from postcode_privacy.postcodes import normalise

POSTCODE_COLUMN = "pcds"


@dataclass(frozen=True)
class GroupSummary:
    """Utility for one group of postcodes."""

    group: str
    count: int
    median_km: float
    p95_km: float
    area_preserved: float
    median_self_probability: float


def aligned_columns(
    onspd: Path, postcodes: npt.NDArray[np.str_], columns: list[str]
) -> dict[str, npt.NDArray[np.str_]]:
    """Read several ONSPD columns at once, in the graph's node order.

    ONSPD rows are not in the graph's order, so values are looked up by
    postcode rather than zipped positionally; mismatching them would attribute
    every measurement to the wrong place. A postcode absent from the source
    gets an empty string, which is visible, rather than a neighbour's value.

    Several columns in one pass because the national file is over a gigabyte
    and reading it once per column is the dominant cost of an evaluation.
    """
    lookup: dict[str, tuple[str, ...]] = {}
    with Path(onspd).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [
            name
            for name in columns
            if reader.fieldnames is None or name not in reader.fieldnames
        ]
        if missing:
            raise KeyError(f"column {missing[0]!r} is not in {onspd}")
        for row in reader:
            lookup[normalise(row[POSTCODE_COLUMN])] = tuple(
                row[name].strip() for name in columns
            )

    blank = ("",) * len(columns)
    rows = [lookup.get(str(name), blank) for name in postcodes]
    return {
        column: np.array([row[index] for row in rows])
        for index, column in enumerate(columns)
    }


def aligned_column(
    onspd: Path, postcodes: npt.NDArray[np.str_], column: str
) -> npt.NDArray[np.str_]:
    """One ONSPD column, in the graph's node order."""
    return aligned_columns(onspd, postcodes, [column])[column]


def area_preservation(
    mechanism: HopMechanism, postcode: str, areas: npt.NDArray[np.str_]
) -> float:
    """Chance the output falls in the same area as the true postcode.

    This is the utility question an analyst actually asks: can I still count
    people by geography? Mass beyond the radius is ignored, because it is held
    below one in a million by construction and because attributing it would
    mean knowing the national distribution of every area.
    """
    graph = mechanism.graph
    source = graph.index_of(postcode)
    distribution = mechanism.distribution(postcode)
    target_area = areas[source]

    preserved = 0.0
    for hop, nodes in enumerate(distribution.shell_nodes):
        matching = nodes[areas[nodes] == target_area]
        if len(matching):
            # Converted to a Python int first: the shell powers are
            # arbitrary-precision integers, and a numpy int64 multiplied by one
            # silently wraps instead of widening.
            weight = int(graph.prior[matching].sum()) * distribution.powers[hop]
            preserved += weight / distribution.total_weight
    return preserved


def summarise_by_group(
    mechanism: HopMechanism,
    postcodes: list[str],
    *,
    areas: npt.NDArray[np.str_],
    groups: npt.NDArray[np.str_],
) -> dict[str, GroupSummary]:
    """Utility for each group, measured over ``postcodes``."""
    collected: dict[str, list[tuple[float, float, float, float]]] = {}
    for postcode in postcodes:
        node = mechanism.graph.index_of(postcode)
        summary = displacement_summary(mechanism, postcode)
        collected.setdefault(str(groups[node]), []).append(
            (
                summary.median_km,
                summary.p95_km,
                area_preservation(mechanism, postcode, areas),
                summary.self_probability,
            )
        )
        # Each postcode is visited once; a cached national distribution is
        # megabytes, so nothing is kept between them.
        mechanism.clear_cache()

    return {
        group: GroupSummary(
            group=group,
            count=len(rows),
            median_km=float(np.median([row[0] for row in rows])),
            p95_km=float(np.quantile([row[1] for row in rows], 0.95)),
            area_preserved=float(np.median([row[2] for row in rows])),
            median_self_probability=float(np.median([row[3] for row in rows])),
        )
        for group, rows in collected.items()
    }


# England and Wales use ONS 2021 codes prefixed U or R; Scotland uses the
# Scottish Government's numeric classification, where 1 and 2 are urban;
# Northern Ireland carries no indicator at all. Harmonising three schemes into
# two words is necessarily coarse, and cross-national comparisons drawn from it
# are not like-for-like.
UNCLASSIFIED = "unclassified"


def urban_or_rural(indicator: str, country: str) -> str:
    """A coarse urban/rural class, harmonised across the three nations."""
    if not indicator or country.startswith("N"):
        return UNCLASSIFIED
    if indicator[0].isdigit():
        return "urban" if indicator[0] in "12" else "rural"
    return "urban" if indicator.startswith("U") else "rural"
