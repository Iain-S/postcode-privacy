"""Measure the epsilon equivalent to truncating a postcode, and cache it.

Each postcode costs eighteen bisection steps on a graph of 1.7 million nodes,
so the result is computed once into a committed JSON file and the figure reads
that. The graph's source hash travels with the numbers: a figure quoting a
measurement without the artefact behind it is an assertion with decimal points.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from postcode_privacy import load_graph
from postcode_privacy.evaluate.comparison import equivalent_epsilon, outward_groups
from postcode_privacy.evaluate.utility import aligned_columns, urban_or_rural

ONSPD = Path("data/ONSPD_AUG_2026_UK.csv")
GRAPH = Path("data/uk.ppg")
CACHE = Path("figures/data/equivalent.json")
PER_GROUP = 12
SEED = 0


def main() -> None:
    graph = load_graph(GRAPH)
    groups = outward_groups(graph.postcodes)
    columns = aligned_columns(ONSPD, graph.postcodes, ["ruc21ind", "ctry26cd"])
    classes = np.array(
        [
            urban_or_rural(code, country)
            for code, country in zip(
                columns["ruc21ind"].tolist(), columns["ctry26cd"].tolist(), strict=True
            )
        ]
    )

    rng = np.random.default_rng(SEED)
    measured: list[dict[str, object]] = []
    for group in ("urban", "rural"):
        pool = np.flatnonzero(classes == group)
        for node in rng.choice(pool, size=PER_GROUP, replace=False).tolist():
            try:
                result = equivalent_epsilon(
                    graph, str(graph.postcodes[node]), groups=groups
                )
            except ValueError:
                continue
            measured.append({"group": group, **asdict(result)})
            print(
                f"  {group:<6} {result.postcode:<9} eps {result.epsilon:.3f}",
                flush=True,
            )

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {
                "seed": SEED,
                "per_group": PER_GROUP,
                "graph": asdict(graph.provenance) if graph.provenance else {},
                "results": measured,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {CACHE} with {len(measured)} measurements")


if __name__ == "__main__":
    main()
