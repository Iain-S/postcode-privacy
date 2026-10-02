"""How much does exposure actually vary between urban and rural?

This exists because the first answer was wrong. A sample of 25 postcodes per
group gave a ratio of 1.03x, a sample of 15 gave 2.1x, and that disagreement
meant neither was trustworthy. A point estimate from a small sample was
promoted to the central claim of the documentation on the strength of one draw.

So this takes a larger sample and reports percentiles. The spread within each
group turns out to be larger than the difference between them, which no small
sample could have shown.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from postcode_privacy import HopMechanism, load_graph
from postcode_privacy.evaluate.utility import aligned_columns, urban_or_rural

ONSPD = Path("data/ONSPD_AUG_2026_UK.csv")
CACHE = Path("figures/data/exposure.json")
PER_GROUP = 150
EPSILON = 1.0
SEED = 0
PERCENTILES = (10, 25, 50, 75, 90)


def main() -> None:
    graph = load_graph("data/uk.ppg")
    columns = aligned_columns(ONSPD, graph.postcodes, ["ruc21ind", "ctry26cd"])
    classes = np.array(
        [
            urban_or_rural(code, country)
            for code, country in zip(
                columns["ruc21ind"].tolist(), columns["ctry26cd"].tolist(), strict=True
            )
        ]
    )

    mechanism = HopMechanism(graph, epsilon=EPSILON)
    rng = np.random.default_rng(SEED)
    summary: dict[str, dict[str, float]] = {}
    for group in ("urban", "rural"):
        pool = np.flatnonzero(classes == group)
        values = []
        for node in rng.choice(pool, size=PER_GROUP, replace=False).tolist():
            values.append(
                mechanism.distribution(str(graph.postcodes[node])).self_probability
            )
            mechanism.clear_cache()
        quantiles = np.percentile(np.array(values), PERCENTILES)
        summary[group] = {
            f"p{pct}": float(value)
            for pct, value in zip(PERCENTILES, quantiles, strict=True)
        }
        print(
            f"{group:<6} "
            + "  ".join(
                f"p{pct} {value:.3%}"
                for pct, value in zip(PERCENTILES, quantiles, strict=True)
            )
        )

    ratio = summary["urban"]["p50"] / summary["rural"]["p50"]
    print(f"\nratio of medians urban/rural: {ratio:.2f}x")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {
                "epsilon": EPSILON,
                "per_group": PER_GROUP,
                "seed": SEED,
                "median_ratio": ratio,
                "self_probability": summary,
                "graph": asdict(graph.provenance) if graph.provenance else {},
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {CACHE}")


if __name__ == "__main__":
    main()
