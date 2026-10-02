"""Turn epsilon into consequences a reader can weigh.

Nobody has intuition for "epsilon 0.5 per hop". This measures what a handful of
values actually do, so the documentation can offer a table of outcomes instead
of a parameter.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from postcode_privacy import HopMechanism, load_graph
from postcode_privacy.evaluate.utility import (
    UNCLASSIFIED,
    aligned_columns,
    summarise_by_group,
    urban_or_rural,
)

ONSPD = Path("data/ONSPD_AUG_2026_UK.csv")
CACHE = Path("figures/data/translation.json")
EPSILONS = (0.3, 0.5, 1.0, 2.0)
PER_GROUP = 15
SEED = 0


def main() -> None:
    graph = load_graph("data/uk.ppg")
    columns = aligned_columns(
        ONSPD, graph.postcodes, ["ruc21ind", "ctry26cd", "lsoa21cd"]
    )
    groups = np.array(
        [
            urban_or_rural(code, country)
            for code, country in zip(
                columns["ruc21ind"].tolist(), columns["ctry26cd"].tolist(), strict=True
            )
        ]
    )

    # One sample, reused at every epsilon, so the rows of the table differ only
    # in the parameter rather than in which postcodes were drawn.
    rng = np.random.default_rng(SEED)
    chosen: list[str] = []
    for group in ("urban", "rural"):
        pool = np.flatnonzero(groups == group)
        chosen += [
            str(graph.postcodes[i])
            for i in rng.choice(pool, size=PER_GROUP, replace=False)
        ]

    runs = []
    for epsilon in EPSILONS:
        mechanism = HopMechanism(graph, epsilon=epsilon)
        summaries = summarise_by_group(
            mechanism, chosen, areas=columns["lsoa21cd"], groups=groups
        )
        runs.append(
            {
                "epsilon": epsilon,
                "radius": mechanism.radius,
                "groups": {
                    name: asdict(row)
                    for name, row in summaries.items()
                    if name != UNCLASSIFIED
                },
            }
        )
        urban, rural = runs[-1]["groups"]["urban"], runs[-1]["groups"]["rural"]
        for name, row in (("urban", urban), ("rural", rural)):
            print(
                f"  eps {epsilon:<5} radius {mechanism.radius:<4} {name:<6}"
                f" median {row['median_km']:>7.2f} km"
                f"  same LSOA {row['area_preserved']:>6.1%}"
                f"  self {row['median_self_probability']:>6.2%}",
                flush=True,
            )

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {
                "per_group": PER_GROUP,
                "seed": SEED,
                "graph": asdict(graph.provenance) if graph.provenance else {},
                "runs": runs,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {CACHE}")


if __name__ == "__main__":
    main()
