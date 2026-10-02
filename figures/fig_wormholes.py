"""The edges that crossed open sea, and what the islands look like without them.

Delaunay tiles the convex hull, so it triangulates across every concavity: the
North Sea, the Irish Sea, the Channel. The top panel draws every edge the
fifty-kilometre cut removes. The lower panels show two island groups as they
stand afterwards, connected to the mainland by the shortest real crossing
rather than by a wormhole to the far end of the country.
"""

from __future__ import annotations

import numpy as np

from figures.style import THEMES, Theme, apply, save
from postcode_privacy import load_graph
from postcode_privacy.graph.build import DEFAULT_MAX_EDGE_KM, delaunay_edges
from postcode_privacy.graph.prune import edge_lengths

# Centre and half-width in metres, chosen from the islands' own coordinates.
# Scilly is framed wide enough to include the Cornish mainland, because the
# point of the panel is the crossing it keeps.
CLOSE_UPS = (
    ("Scilly and west Cornwall", 118_000, 22_000, 44_000),
    ("Mull and the Inner Hebrides", 138_000, 742_000, 46_000),
)


def _segments(edges, graph):
    return [
        [
            (graph.eastings[a], graph.northings[a]),
            (graph.eastings[b], graph.northings[b]),
        ]
        for a, b in edges
    ]


def build_figure(theme: Theme) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    apply(theme)
    graph = load_graph("data/uk.ppg")
    all_edges = delaunay_edges(graph.eastings, graph.northings)
    lengths = edge_lengths(all_edges, graph.eastings, graph.northings) / 1000
    cut = all_edges[lengths > DEFAULT_MAX_EDGE_KM]

    figure = plt.figure(figsize=(8.2, 10.2))
    grid = figure.add_gridspec(2, 2, height_ratios=[1.45, 1], hspace=0.14, wspace=0.1)
    national = figure.add_subplot(grid[0, :])

    national.scatter(
        graph.eastings,
        graph.northings,
        s=0.03,
        c=theme.muted,
        linewidths=0,
        rasterized=True,
        zorder=1,
    )
    national.add_collection(
        LineCollection(
            _segments(cut, graph),
            colors=theme.series[1],
            linewidths=0.9,
            alpha=0.85,
            zorder=2,
        )
    )
    national.set_title(
        f"{len(cut):,} edges longer than {DEFAULT_MAX_EDGE_KM:g} km, "
        "every one across water",
        color=theme.text,
        pad=8,
    )

    for axis, (name, east, north, span) in zip(
        [figure.add_subplot(grid[1, 0]), figure.add_subplot(grid[1, 1])],
        CLOSE_UPS,
        strict=True,
    ):
        inside = (np.abs(graph.eastings - east) < span) & (
            np.abs(graph.northings - north) < span
        )
        local = np.flatnonzero(inside)
        keep = np.isin(all_edges[:, 0], local) & np.isin(all_edges[:, 1], local)
        kept = all_edges[keep & (lengths <= DEFAULT_MAX_EDGE_KM)]

        axis.add_collection(
            LineCollection(
                _segments(kept, graph),
                colors=theme.series[0],
                linewidths=0.4,
                alpha=0.6,
                zorder=2,
            )
        )
        axis.scatter(
            graph.eastings[local],
            graph.northings[local],
            s=1.2,
            c=theme.text,
            linewidths=0,
            rasterized=True,
            zorder=3,
        )
        axis.set_xlim(east - span, east + span)
        axis.set_ylim(north - span, north + span)
        axis.set_title(f"{name}, after the cut", color=theme.text, pad=6)

    for axis in figure.get_axes():
        axis.set_aspect("equal")
        axis.set_xticks([])
        axis.set_yticks([])
        for spine in axis.spines.values():
            spine.set_color(theme.muted)

    figure.suptitle(
        "Triangulating a coastline invents neighbours across the sea",
        color=theme.text,
        fontsize=13,
        fontweight="bold",
        y=0.945,
    )
    figure.text(
        0.5,
        0.055,
        "The longest reached 920 km, Great Yarmouth to Shetland. Removing them cut "
        "the rural p95 displacement\nfrom 260 km to 61 km and the Isle of Lewis "
        "median from 308 km to 10 km, with no change in protection.",
        ha="center",
        color=theme.secondary,
        fontsize=9,
    )
    print("  ", save(figure, "wormholes", theme, raster=True))


if __name__ == "__main__":
    for theme in THEMES:
        build_figure(theme)
