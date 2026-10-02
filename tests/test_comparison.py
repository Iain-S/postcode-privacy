"""Comparing the mechanism against truncating a postcode."""

import numpy as np
import pytest

from postcode_privacy import PostcodeGraph
from postcode_privacy.evaluate.comparison import (
    equivalent_epsilon,
    outward_groups,
    truncation_error_km,
)

N = 40


def line() -> PostcodeGraph:
    # Two outward codes, twenty postcodes each, a kilometre apart.
    postcodes = [f"A{i // 20 + 1} {i % 20 // 10}AA" for i in range(N)]
    postcodes = [f"A{i // 20 + 1} {i % 10}A{chr(65 + i % 20 // 10)}" for i in range(N)]
    return PostcodeGraph.from_edges(
        postcodes=np.array(sorted(postcodes)),
        edges=np.array([[i, i + 1] for i in range(N - 1)], dtype=np.int64),
        prior=np.ones(N, dtype=np.int64),
        eastings=np.arange(N, dtype=np.int64) * 1000,
        northings=np.zeros(N, dtype=np.int64),
    )


def test_postcodes_are_grouped_by_their_outward_code() -> None:
    groups = outward_groups(line().postcodes)

    assert set(groups) == {"A1", "A2"}
    assert sum(len(members) for members in groups.values()) == N


def test_truncation_error_is_the_distance_to_a_random_neighbour_in_the_district() -> (
    None
):
    # What an analyst loses by being told only the outward code: the best they
    # can do is a postcode drawn from the district.
    graph = line()

    error = truncation_error_km(graph, "A1 0AA", groups=outward_groups(graph.postcodes))

    # Twenty postcodes a kilometre apart: mean distance from the first is about
    # 9.5 km, and certainly between 5 and 15.
    assert 5.0 < error < 15.0


def test_an_equivalent_epsilon_is_found_and_is_positive() -> None:
    graph = line()

    result = equivalent_epsilon(graph, "A1 0AA", groups=outward_groups(graph.postcodes))

    assert result.epsilon > 0
    assert result.truncation_km == pytest.approx(
        truncation_error_km(graph, "A1 0AA", groups=outward_groups(graph.postcodes))
    )


def test_the_equivalent_epsilon_actually_matches_the_truncation_error() -> None:
    # The whole point: at this epsilon the mechanism displaces people about as
    # far as truncation leaves an analyst guessing.
    graph = line()
    groups = outward_groups(graph.postcodes)

    result = equivalent_epsilon(graph, "A1 0AA", groups=groups)

    assert result.achieved_km == pytest.approx(result.truncation_km, rel=0.3)


def test_a_district_with_one_postcode_has_no_equivalent() -> None:
    # Truncation hides a lone postcode among nobody, so there is no epsilon
    # that matches it and saying so is better than returning a number.
    graph = PostcodeGraph.from_edges(
        postcodes=np.array(["A1 1AA", "B1 1BB", "C1 1CC"]),
        edges=np.array([[0, 1], [1, 2]], dtype=np.int64),
        prior=np.ones(3, dtype=np.int64),
        eastings=np.array([0, 1000, 2000], dtype=np.int64),
        northings=np.zeros(3, dtype=np.int64),
    )

    with pytest.raises(ValueError, match="alone"):
        equivalent_epsilon(graph, "A1 1AA", groups=outward_groups(graph.postcodes))
