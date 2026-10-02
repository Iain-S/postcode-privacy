"""What a hop means, in a city and in a glen.

The central claim of this library in one figure. The top row fixes the number
of hops and lets the map extent fall where it may; the bottom row fixes the map
extent and lets the hop count fall where it may. Together they show that a hop
is a constant amount of *exposure* and a wildly variable number of metres,
which is the whole design.
"""

from __future__ import annotations

import numpy as np

from figures.style import THEMES, Theme, apply, ramp, save
from postcode_privacy import load_graph

HOPS = 6
WINDOW_KM = 4.0
URBAN = "LS6 1AA"
RURAL = "IV27 4JB"


def shells(graph, postcode: str, hops: int):
    nodes, distance = graph.adjacency.ball(source=graph.index_of(postcode), radius=hops)
    return nodes, distance


def panel(ax, graph, postcode: str, theme: Theme, *, window_m: float | None) -> float:
    source = graph.index_of(postcode)
    nodes, distance = shells(graph, postcode, HOPS)
    centre = (float(graph.eastings[source]), float(graph.northings[source]))

    if window_m is None:
        spread = np.max(
            np.abs(
                np.column_stack(
                    [
                        graph.eastings[nodes] - centre[0],
                        graph.northings[nodes] - centre[1],
                    ]
                )
            )
        )
        window_m = float(spread) * 1.15

    # Everything nearby that is NOT in the ball, so the ball reads as a
    # selection from a populated place rather than as the only thing there.
    near = np.flatnonzero(
        (np.abs(graph.eastings - centre[0]) < window_m)
        & (np.abs(graph.northings - centre[1]) < window_m)
    )
    ax.scatter(
        graph.eastings[near],
        graph.northings[near],
        s=1.5,
        c=theme.muted,
        linewidths=0,
        rasterized=True,
        zorder=1,
    )

    inside = np.abs(graph.eastings[nodes] - centre[0]) < window_m
    inside &= np.abs(graph.northings[nodes] - centre[1]) < window_m
    ax.scatter(
        graph.eastings[nodes][inside],
        graph.northings[nodes][inside],
        s=5,
        c=distance[inside],
        cmap=ramp(theme),
        vmin=0,
        vmax=HOPS,
        linewidths=0,
        rasterized=True,
        zorder=2,
    )
    ax.scatter(
        *centre,
        s=70,
        facecolor="none",
        edgecolor=theme.series[1],
        linewidths=1.8,
        zorder=3,
    )

    ax.set_xlim(centre[0] - window_m, centre[0] + window_m)
    ax.set_ylim(centre[1] - window_m, centre[1] + window_m)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(theme.muted)

    # A scale bar, because the entire point is how many metres a hop covers.
    bar_m = 10 ** np.floor(np.log10(window_m))
    if bar_m * 2 < window_m:
        bar_m *= 2
    x0 = centre[0] - window_m * 0.9
    y0 = centre[1] - window_m * 0.88
    ax.plot([x0, x0 + bar_m], [y0, y0], color=theme.text, linewidth=2, zorder=4)
    label = f"{bar_m / 1000:g} km" if bar_m >= 1000 else f"{bar_m:g} m"
    ax.text(x0, y0 + window_m * 0.065, label, color=theme.text, fontsize=8)

    # Always stated. A nearly empty panel is the finding, not a failed render,
    # and the count is what makes the comparison between panels concrete.
    ax.text(
        centre[0] - window_m * 0.9,
        centre[1] + window_m * 0.82,
        f"{int(inside.sum())} postcodes within {HOPS} hops, in view",
        color=theme.secondary,
        fontsize=8.5,
    )
    return window_m


def build(theme: Theme) -> None:
    import matplotlib.pyplot as plt

    apply(theme)
    graph = load_graph("data/uk.ppg")
    figure, axes = plt.subplots(2, 2, figsize=(8.4, 9.2))

    for column, postcode in enumerate((URBAN, RURAL)):
        used = panel(axes[0][column], graph, postcode, theme, window_m=None)
        axes[0][column].set_title(
            f"{postcode}\n{HOPS} hops · view {used * 2 / 1000:,.0f} km across",
            color=theme.text,
            pad=8,
        )
        panel(axes[1][column], graph, postcode, theme, window_m=WINDOW_KM * 1000)
        axes[1][column].set_title(
            f"{postcode}\nsame {WINDOW_KM:g} km view", color=theme.text, pad=8
        )

    figure.suptitle(
        "A hop is a constant amount of exposure, not a constant distance",
        color=theme.text,
        fontsize=13,
        fontweight="bold",
        y=0.99,
    )

    # A sequential ramp needs its scale shown; the caption alone is not enough.
    mappable = plt.cm.ScalarMappable(
        norm=plt.Normalize(vmin=0, vmax=HOPS), cmap=ramp(theme)
    )
    bar = figure.colorbar(
        mappable,
        ax=axes,
        orientation="horizontal",
        fraction=0.03,
        pad=0.04,
        aspect=44,
        ticks=range(HOPS + 1),
    )
    bar.set_label("hop distance from the true postcode", color=theme.secondary)
    bar.outline.set_visible(False)
    bar.ax.tick_params(color=theme.muted)

    figure.text(
        0.5,
        0.012,
        "The ringed mark is the true postcode; grey marks are other postcodes in "
        "view.\nTop row: the same six hops, each at its own scale. Bottom row: the "
        "same four-kilometre window.",
        ha="center",
        color=theme.secondary,
        fontsize=9,
    )
    print("  ", save(figure, "hops", theme, raster=True))


if __name__ == "__main__":
    for theme in THEMES:
        build(theme)
