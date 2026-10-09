"""Golden determinism tests.

These pin the library's headline promise: **a given subject always maps to the
same output postcode**, on every platform and in every future version.

If a change here makes one of these tests fail, the correct response is almost
never to update the expected values. A changed golden means that every subject
already released under the old behaviour would now be perturbed differently, so
the two releases together leak more than one -- the promise that epsilon is
spent once is broken. Treat a failure as a defect in the change, not in the test.

The values below were produced by the implementation and are deliberately
arbitrary. Their worth is not that they are "right" but that they are *fixed*;
the mutation check in the suite notes below confirms they have teeth.

The continuous integration operating-system matrix exists for these tests. Node
ordering, integer weights and the keyed PRF are all meant to be bit-identical
across platforms, and only running the same literals on Linux and macOS proves it.

These literals were last changed deliberately, for issue #6: the exponential
factors are now rounded up from one another rather than each from scratch, which
changes the total weight the PRF draws against and so reshuffles every output.
That is exactly the kind of change the table in CHANGELOG.md calls
output-changing, and it is recorded there.
"""

import numpy as np
import pytest

from postcode_privacy import HopMechanism, Key, PostcodeGraph
from postcode_privacy.graph.artefact import load_graph, save_graph
from postcode_privacy.graph.provenance import Provenance

# A path of twenty postcodes. A path rather than a ring because its diameter
# exceeds a small radius, which is what lets the tail branch of the sampler be
# exercised at all.
N_NODES = 20
POSTCODES = [f"A{i:03d} 1AA" for i in range(N_NODES)]
EDGES = np.array([[i, i + 1] for i in range(N_NODES - 1)], dtype=np.int64)

# Deliberately non-uniform, so that the within-shell draw has something to
# choose between. A uniform prior would hide a bug in that stage.
PRIOR = np.array([1 + (7 * i) % 5 for i in range(N_NODES)], dtype=np.int64)

KEY_MATERIAL = bytes(range(32))
SUBJECTS = [f"subject-{i}" for i in range(8)]
SOURCE = "A010 1AA"

# The tail goldens below use a deliberately small radius, because that is the
# only way to leave mass outside the ball and exercise the tail branch at all.
# The mechanism rightly warns about that, and here it is expected, not a defect.
pytestmark = pytest.mark.filterwarnings(
    "ignore::postcode_privacy.mechanism.mechanism.RadiusTooSmallWarning"
)

# Radius 66 covers the whole graph, so every draw lands in a shell.
GOLDEN_SHELL_BRANCH = [
    "A009 1AA",
    "A017 1AA",
    "A008 1AA",
    "A017 1AA",
    "A009 1AA",
    "A005 1AA",
    "A012 1AA",
    "A014 1AA",
]

# Radius 3 leaves a third of the mass outside the ball, so the tail branch --
# the rejection-sampled draw from the prior -- is genuinely exercised here.
GOLDEN_TAIL_BRANCH = [
    "A016 1AA",
    "A012 1AA",
    "A005 1AA",
    "A004 1AA",
    "A010 1AA",
    "A010 1AA",
    "A012 1AA",
    "A007 1AA",
]


def fixture_graph() -> PostcodeGraph:
    return PostcodeGraph.from_edges(
        postcodes=np.array(POSTCODES),
        edges=EDGES,
        prior=PRIOR,
        eastings=np.arange(N_NODES, dtype=np.int64) * 100,
        northings=np.zeros(N_NODES, dtype=np.int64),
    )


def outputs(graph: PostcodeGraph, **kwargs: object) -> list[str]:
    mechanism = HopMechanism(graph, **kwargs)  # ty: ignore[invalid-argument-type]
    key = Key.from_bytes(KEY_MATERIAL)
    return [
        mechanism.perturb(SOURCE, subject_id=subject, key=key) for subject in SUBJECTS
    ]


def test_outputs_are_fixed_when_every_draw_lands_in_a_shell() -> None:
    assert outputs(fixture_graph(), epsilon=0.5) == GOLDEN_SHELL_BRANCH


def test_outputs_are_fixed_when_draws_fall_outside_the_ball() -> None:
    assert outputs(fixture_graph(), epsilon=2.0, radius=3) == GOLDEN_TAIL_BRANCH


def test_the_tail_branch_is_actually_exercised() -> None:
    # Guards the test above rather than the library. If a future change made the
    # radius cover the graph, the tail golden would silently become a duplicate
    # of the shell case and stop testing the branch it was written for.
    mechanism = HopMechanism(fixture_graph(), epsilon=2.0, radius=3)

    assert mechanism.distribution(SOURCE).teleport_probability > 0.1


def test_saving_and_reloading_the_graph_changes_no_output(tmp_path) -> None:
    # Node order, the prior and the adjacency all survive the artefact round
    # trip bit-identically, or a subject's output would depend on whether the
    # graph came from a build or from a file.
    provenance = Provenance(
        source="fixture",
        source_sha256="0" * 64,
        gb_only=False,
        max_edge_km=None,
        prune_alpha=None,
        library_version="test",
        prior_kind="population",
        prior_total=int(PRIOR.sum()),
    )
    path = tmp_path / "fixture.ppg"
    save_graph(fixture_graph(), path, provenance=provenance)

    assert outputs(load_graph(path), epsilon=0.5) == GOLDEN_SHELL_BRANCH
    assert outputs(load_graph(path), epsilon=2.0, radius=3) == GOLDEN_TAIL_BRANCH


@pytest.mark.parametrize(
    ("epsilon", "radius", "golden"),
    [(0.5, None, GOLDEN_SHELL_BRANCH), (2.0, 3, GOLDEN_TAIL_BRANCH)],
)
def test_a_different_key_gives_different_outputs(
    epsilon: float, radius: int | None, golden: list[str]
) -> None:
    # Without this, goldens that had accidentally stopped depending on the key
    # would still pass.
    mechanism = HopMechanism(fixture_graph(), epsilon=epsilon, radius=radius)
    other = Key.from_bytes(bytes(range(1, 33)))

    produced = [
        mechanism.perturb(SOURCE, subject_id=subject, key=other) for subject in SUBJECTS
    ]

    assert produced != golden
