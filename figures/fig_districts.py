"""What truncating a postcode actually hides you among.

The case against truncation in one chart. Every outward-code district in the
country, by the number of residents it contains, on a log axis because that is
the only scale on which 2 and 169,419 both fit.
"""

from __future__ import annotations

import numpy as np

from figures.style import THEMES, Theme, apply, save
from postcode_privacy import load_graph
from postcode_privacy.evaluate.comparison import outward_groups

SINGLE = ("PA62", "PA63", "PA74", "PH30", "PH42", "PH43", "PH44", "TR22", "TR23")


def build_figure(theme: Theme) -> None:
    import matplotlib.pyplot as plt

    apply(theme)
    graph = load_graph("data/uk.ppg")
    groups = outward_groups(graph.postcodes)
    names = list(groups)
    people = np.array([int(graph.prior[nodes].sum()) for nodes in groups.values()])

    figure, ax = plt.subplots(figsize=(8.6, 4.8))
    bins = np.logspace(0, np.log10(people.max() * 1.05), 48)
    ax.hist(
        people,
        bins=bins,
        color=theme.series[0],
        edgecolor=theme.surface,
        linewidth=0.6,
        zorder=2,
    )
    ax.set_xscale("log")
    ax.set_xlabel("residents in the district a truncated postcode reveals")
    ax.set_ylabel("outward-code districts")
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)

    # The nine districts that are a single postcode, where truncation discloses
    # the exact unit. Marked rather than described, because they are the point.
    single = np.array([people[names.index(n)] for n in SINGLE if n in names])
    ax.scatter(
        single,
        np.full(len(single), 14),
        s=26,
        color=theme.series[1],
        zorder=4,
        clip_on=False,
    )
    ax.annotate(
        f"{len(single)} districts are a SINGLE postcode:\n"
        "truncation discloses the exact unit",
        xy=(float(np.median(single)), 14),
        xytext=(3.2, 150),
        color=theme.series[1],
        fontsize=9,
        arrowprops={"arrowstyle": "-", "color": theme.series[1], "linewidth": 1},
    )

    for label, value, offset in (
        ("PH30\n2 residents", int(people.min()), 60),
        (f"CR0, Croydon\n{people.max():,} residents", int(people.max()), 60),
    ):
        ax.annotate(
            label,
            xy=(value, 2),
            xytext=(value, offset),
            ha="center",
            color=theme.secondary,
            fontsize=8.5,
            arrowprops={"arrowstyle": "-", "color": theme.muted, "linewidth": 0.8},
        )

    median = float(np.median(people))
    ax.axvline(
        median, color=theme.secondary, linewidth=1, linestyle=(0, (4, 3)), zorder=3
    )
    ax.text(
        median * 1.12,
        ax.get_ylim()[1] * 0.92,
        f"median {median:,.0f}",
        color=theme.secondary,
        fontsize=8.5,
    )

    ax.set_title(
        "The same operation, protection differing by a factor of 764",
        color=theme.text,
        pad=10,
    )
    figure.text(
        0.5,
        -0.06,
        f"All {len(people):,} outward-code districts in the August 2026 build. "
        "1st percentile 101 residents, 99th 77,018.\nAgainst this, the "
        "mechanism's self-probability differs 1.31x between urban and rural "
        "medians.",
        ha="center",
        color=theme.secondary,
        fontsize=9,
    )
    print("  ", save(figure, "districts", theme, raster=False))


if __name__ == "__main__":
    for theme in THEMES:
        build_figure(theme)
