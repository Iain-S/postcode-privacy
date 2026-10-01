"""Compressed adjacency and the breadth-first ball."""

import numpy as np

from postcode_privacy.graph.adjacency import Adjacency

# 0 -- 1 -- 2 -- 3,  plus 1 -- 4
PATH_EDGES = np.array([[0, 1], [1, 2], [2, 3], [1, 4]], dtype=np.int64)


def test_neighbours_are_recovered_in_both_directions() -> None:
    adjacency = Adjacency.from_edges(PATH_EDGES, n_nodes=5)

    assert sorted(adjacency.neighbours(1)) == [0, 2, 4]
    assert sorted(adjacency.neighbours(3)) == [2]


def test_the_ball_reports_each_node_once_with_its_hop_distance() -> None:
    adjacency = Adjacency.from_edges(PATH_EDGES, n_nodes=5)

    nodes, hops = adjacency.ball(source=0, radius=2)

    assert dict(zip(nodes.tolist(), hops.tolist(), strict=True)) == {
        0: 0,
        1: 1,
        2: 2,
        4: 2,
    }


def test_a_radius_of_zero_is_the_source_alone() -> None:
    adjacency = Adjacency.from_edges(PATH_EDGES, n_nodes=5)

    nodes, hops = adjacency.ball(source=3, radius=0)

    assert nodes.tolist() == [3]
    assert hops.tolist() == [0]


def test_a_radius_beyond_the_graph_returns_every_node() -> None:
    adjacency = Adjacency.from_edges(PATH_EDGES, n_nodes=5)

    nodes, hops = adjacency.ball(source=0, radius=99)

    assert sorted(nodes.tolist()) == [0, 1, 2, 3, 4]
    assert max(hops.tolist()) == 3
