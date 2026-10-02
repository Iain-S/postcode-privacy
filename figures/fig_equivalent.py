"""What epsilon matches truncating a postcode, and why it is not one number.

A strip plot rather than a bar chart: twenty-four measurements is few enough to
show every one, and showing every one is the point. A bar of the median would
hide the spread, which is the finding.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from figures.style import THEMES, Theme, apply, save

CACHE = Path("figures/data/equivalent.json")
GROUPS = ("urban", "rural")


def build_figure(theme: Theme) -> None:
    import matplotlib.pyplot as plt

    apply(theme)
    payload = json.loads(CACHE.read_text())
    results = payload["results"]

    figure, ax = plt.subplots(figsize=(8.6, 3.9))
    rng = np.random.default_rng(1)

    for row, group in enumerate(GROUPS):
        values = np.array(
            [r["epsilon"] for r in results if r["group"] == group], dtype=float
        )
        # A little vertical jitter so coincident points stay countable.
        jitter = rng.uniform(-0.1, 0.1, size=len(values))
        ax.scatter(
            values,
            np.full(len(values), row) + jitter,
            s=46,
            color=theme.series[row],
            alpha=0.85,
            linewidths=0,
            zorder=3,
        )
        median = float(np.median(values))
        ax.plot(
            [median, median],
            [row - 0.27, row + 0.27],
            color=theme.text,
            linewidth=2.2,
            zorder=4,
        )
        ax.text(
            median,
            row + 0.36,
            f"median {median:.2f}",
            ha="center",
            color=theme.text,
            fontsize=9,
        )
        # Direct-labelled, so identity never rests on colour alone.
        ax.text(
            0.17,
            row,
            group,
            ha="right",
            va="center",
            color=theme.text,
            fontsize=10,
            fontweight="bold",
        )

    ax.set_yticks([])
    ax.set_ylim(-0.6, len(GROUPS) - 0.25)
    ax.set_xlim(0.17, 1.2)
    ax.set_xlabel("epsilon per hop that matches what truncation costs an analyst")
    ax.grid(axis="x", zorder=0)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)

    ax.set_title(
        "No single epsilon is equivalent to truncating a postcode",
        color=theme.text,
        pad=10,
    )
    everything = np.array([r["epsilon"] for r in results])
    figure.text(
        0.5,
        -0.13,
        f"{len(everything)} sampled postcodes. Overall median "
        f"{np.median(everything):.2f}, range {everything.min():.2f} to "
        f"{everything.max():.2f} — a {everything.max() / everything.min():.1f}x "
        "spread.\nThe comparison is on utility cost only, and flatters truncation: "
        "it ignores that truncation's released fact is certain.",
        ha="center",
        color=theme.secondary,
        fontsize=9,
    )
    print("  ", save(figure, "equivalent", theme, raster=False))


if __name__ == "__main__":
    for theme in THEMES:
        build_figure(theme)
