"""What a Bayesian adversary achieves, with a candidate set that contains the truth.

The candidate radius is sized from the measured hop displacement between truth
and output. Earlier runs used radius 3, which at epsilon 0.5 contains the true
postcode only 15% of the time, so "the attacker guessed wrong" mostly meant
"the attacker was never shown the answer". Those are different results and only
one of them is an attacker success rate.

Measured hop distance from truth to output, 60 sampled postcodes:

    epsilon 0.5   median 9   p95 21     radius 3 covers 15%
    epsilon 1.0   median 4   p95 14     radius 3 covers 43%
    epsilon 2.0   median 2   p95  5     radius 3 covers 83%
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from postcode_privacy import HopMechanism, Key, load_graph
from postcode_privacy.evaluate.attack import (
    attack,
    independent_releases,
    keyed_releases,
)

CACHE = Path("figures/data/attack.json")
EPSILON = 2.0
# 100% coverage at this epsilon in the displacement sample above.
CANDIDATE_RADIUS = 10
SAMPLE = 20
SEED = 0
KEY = bytes([0x33]) * 32


def main() -> None:
    graph = load_graph("data/uk.ppg")
    mechanism = HopMechanism(graph, epsilon=EPSILON)
    key = Key.from_bytes(KEY)
    rng = np.random.default_rng(SEED)
    sample = rng.choice(graph.n_nodes, size=SAMPLE, replace=False)

    scenarios = (
        ("one release", 1, True),
        ("twenty independent", 20, True),
        ("twenty keyed", 20, False),
    )
    rows = []
    for label, count, independent in scenarios:
        considered = correct = 0
        ranks: list[int] = []
        truths: list[float] = []
        for node in sample.tolist():
            postcode = str(graph.postcodes[node])
            outputs = (
                independent_releases(mechanism, postcode, count=count, seed=int(node))
                if independent
                else keyed_releases(mechanism, postcode, count=count, key=key)
            )
            result = attack(
                mechanism,
                outputs,
                truth=postcode,
                independent=independent,
                candidate_radius=CANDIDATE_RADIUS,
            )
            mechanism.clear_cache()
            considered += result.truth_considered
            correct += result.correct
            if result.truth_rank is not None and result.truth_probability is not None:
                ranks.append(result.truth_rank)
                truths.append(result.truth_probability)

        rows.append(
            {
                "scenario": label,
                "releases": count,
                "independent": independent,
                "truth_considered": considered,
                "correct": correct,
                "median_rank": float(np.median(ranks)),
                "median_truth_probability": float(np.median(truths)),
            }
        )
        print(
            f"  {label:<20} considered {considered}/{SAMPLE}  "
            f"correct {correct}/{SAMPLE}  median rank {np.median(ranks):.0f}  "
            f"median P(truth) {np.median(truths):.4f}",
            flush=True,
        )

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {
                "epsilon": EPSILON,
                "candidate_radius": CANDIDATE_RADIUS,
                "sample": SAMPLE,
                "seed": SEED,
                "scenarios": rows,
                "graph": asdict(graph.provenance) if graph.provenance else {},
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {CACHE}")


if __name__ == "__main__":
    main()
