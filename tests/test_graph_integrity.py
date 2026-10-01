"""Guards against graphs that silently provide no privacy.

A node that is isolated, or stranded in a tiny component, has almost all of its
output distribution concentrated on its own true value. The mechanism does not
fail, warn, or look unusual -- it simply hands back the secret. This happened for
real: 57,030 postcodes sharing a centroid were isolated by the triangulation,
because Qhull discards duplicate points.

The lesson is not "handle duplicates". It is that the consequence must be
asserted directly, because the next cause will be something else.
"""

import numpy as np
import pytest

from postcode_privacy.graph.build import GraphIntegrityError, check_integrity


def test_an_isolated_node_is_rejected() -> None:
    # Node 2 appears in no edge.
    edges = np.array([[0, 1]], dtype=np.int64)

    with pytest.raises(GraphIntegrityError) as excinfo:
        check_integrity(edges, n_nodes=3)

    assert "isolated" in str(excinfo.value).lower()


def test_a_disconnected_graph_is_rejected() -> None:
    # Two components, neither isolated: still a privacy failure for the smaller.
    edges = np.array([[0, 1], [1, 2], [3, 4]], dtype=np.int64)

    with pytest.raises(GraphIntegrityError) as excinfo:
        check_integrity(edges, n_nodes=5)

    message = str(excinfo.value)
    assert "2" in message, "should report how many components were found"


def test_a_connected_graph_passes() -> None:
    edges = np.array([[0, 1], [1, 2], [2, 3]], dtype=np.int64)

    check_integrity(edges, n_nodes=4)
