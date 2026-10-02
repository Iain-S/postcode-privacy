"""Where people are, and why the country looks the way it does.

Terrain is the reason this figure carries a basemap at all: the empty parts of
the population map are the mountains, and showing that turns "density varies"
into "density varies for a reason". Elevation is relief only -- it carries no
quantity the reader is asked to compare -- so it is drawn in neutral grey, and
the one hue in the figure belongs to the data.
"""

from __future__ import annotations

import numpy as np

from figures.style import THEMES, Theme, apply, ramp, save
from figures.terrain import CELL_M, NATIONAL_HEIGHT_M, NATIONAL_WIDTH_M, build
from postcode_privacy import load_graph

GRID_KM = 5


def build_figure(theme: Theme) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource, LogNorm

    apply(theme)
    graph = load_graph("data/uk.ppg")
    elevation = build()

    figure, axes = plt.subplots(1, 2, figsize=(9.6, 7.4))

    # Hillshade, in grey. Relief is context, not a measurement.
    shaded = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(elevation, nan=0.0), vert_exag=18, dx=CELL_M, dy=CELL_M
    )
    shaded = np.where(np.isnan(elevation), np.nan, shaded)
    extent = (0, NATIONAL_WIDTH_M, 0, NATIONAL_HEIGHT_M)
    for ax in axes:
        ax.imshow(
            shaded,
            extent=extent,
            cmap="Greys_r",
            vmin=-0.15,
            vmax=1.35,
            interpolation="bilinear",
            zorder=1,
        )

    axes[0].set_title("The land (Great Britain)", color=theme.text, pad=8)

    # Residents per 5 km cell, from the population prior the mechanism uses.
    cell = GRID_KM * 1000
    columns = NATIONAL_WIDTH_M // cell
    rows = NATIONAL_HEIGHT_M // cell
    counts = np.zeros((rows, columns))
    np.add.at(
        counts,
        (
            np.clip(graph.northings // cell, 0, rows - 1),
            np.clip(graph.eastings // cell, 0, columns - 1),
        ),
        graph.prior.astype(np.float64),
    )
    counts[counts == 0] = np.nan

    image = axes[1].imshow(
        counts,
        extent=extent,
        origin="lower",
        cmap=ramp(theme),
        norm=LogNorm(vmin=10, vmax=np.nanmax(counts)),
        interpolation="nearest",
        zorder=2,
    )
    axes[1].set_title(f"Residents per {GRID_KM} km cell", color=theme.text, pad=8)

    for ax in axes:
        ax.set_xlim(0, NATIONAL_WIDTH_M)
        ax.set_ylim(0, NATIONAL_HEIGHT_M)
        ax.set_aspect("equal")
        ax.axis("off")

    bar = figure.colorbar(
        image,
        ax=axes,
        orientation="horizontal",
        fraction=0.035,
        pad=0.03,
        aspect=44,
    )
    bar.set_label(f"residents per {GRID_KM} km cell (log scale)", color=theme.secondary)
    bar.outline.set_visible(False)
    bar.ax.tick_params(color=theme.muted)

    figure.suptitle(
        "Population is as uneven as the ground it sits on",
        color=theme.text,
        fontsize=13,
        fontweight="bold",
        y=0.95,
    )
    figure.text(
        0.5,
        0.025,
        "Relief: OS Terrain 50, Ordnance Survey, Open Government Licence \u2014 Great "
        "Britain only, which is why\nNorthern Ireland appears on the right but not the "
        "left. Population: the prior this library uses, from the\n2021 and 2022 "
        "censuses. The emptiest places are the highest ones.",
        ha="center",
        color=theme.secondary,
        fontsize=9,
    )
    print("  ", save(figure, "density", theme, raster=True))


if __name__ == "__main__":
    for theme in THEMES:
        build_figure(theme)
