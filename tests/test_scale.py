"""Throughput at dataset scale.

The batch path exists so that a large file costs one ball expansion per
*distinct* postcode rather than one per row. That is a structural property, so
it is asserted structurally; the timing is a loose backstop that only a genuine
regression -- expanding per row again -- could trip.
"""

import time

import numpy as np
import pytest

from postcode_privacy import HopMechanism, Key, PostcodeGraph

N_NODES = 2_000
N_ROWS = 1_000_000
N_DISTINCT = 1_000

# Generous by two orders of magnitude. Expanding the ball per row instead of
# per distinct postcode would be a thousand times more work and miss this by a
# wide margin, which is the only failure worth catching here.
TIME_BUDGET_SECONDS = 180.0


def fixture_postcodes(count: int) -> list[str]:
    """Well-formed postcodes, sorted.

    Naively numbering past 999 produces `A1000 1AA`, which is eight characters
    and not a postcode at all. Two letters and a digit keep every value valid.
    """
    values = [
        f"{chr(65 + index // 260)}{chr(65 + (index // 10) % 26)}{index % 10} 1AA"
        for index in range(count)
    ]
    return sorted(values)


def grid_graph() -> PostcodeGraph:
    side = int(np.sqrt(N_NODES)) + 1
    postcodes = np.array(fixture_postcodes(N_NODES))
    edges = []
    for node in range(N_NODES):
        _, column = divmod(node, side)
        right, below = node + 1, node + side
        if column + 1 < side and right < N_NODES:
            edges.append([node, right])
        if below < N_NODES:
            edges.append([node, below])
    return PostcodeGraph.from_edges(
        postcodes=postcodes,
        edges=np.array(edges, dtype=np.int64),
        prior=np.ones(N_NODES, dtype=np.int64),
    )


@pytest.mark.slow
def test_a_million_rows_cost_one_ball_expansion_per_distinct_postcode() -> None:
    mechanism = HopMechanism(grid_graph(), epsilon=2.0)
    key = Key.from_bytes(b"\x07" * 32)
    rng = np.random.default_rng(0)
    available = fixture_postcodes(N_NODES)[:N_DISTINCT]
    chosen = rng.integers(0, N_DISTINCT, size=N_ROWS)
    postcodes = [available[index] for index in chosen]
    subjects = [f"p{index}" for index in range(N_ROWS)]

    started = time.monotonic()
    outputs = mechanism.perturb_many(postcodes, subjects, key=key)
    elapsed = time.monotonic() - started

    assert len(outputs) == N_ROWS
    assert all(outputs)
    # The structural claim: one cached distribution per distinct postcode.
    assert mechanism.cache_size == len(set(postcodes))
    assert elapsed < TIME_BUDGET_SECONDS, (
        f"1,000,000 rows took {elapsed:.0f}s; the batch path is probably "
        "expanding the ball per row again"
    )
