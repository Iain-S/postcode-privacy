"""Shared figure styling.

Dark mode is a selected palette rather than an inverted one: the same hues
re-stepped against the dark surface, as the design method requires. Every figure
is therefore rendered twice and the documentation picks per theme.

The categorical slots used here were validated with the method's own checker on
the all-pairs test, which is the right one for scatter and map forms:
    blue #2a78d6 / orange #eb6834 / aqua #1baf7a   (light)
    blue #3987e5 / orange #d95926 / aqua #199e70   (dark)
The aqua falls below 3:1 against the light surface, so anything drawn in it
carries a visible label rather than relying on colour alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

OUTPUT = Path("docs/figures")


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    text: str
    secondary: str
    muted: str
    series: tuple[str, str, str]
    # Sequential blue, light to dark, stepped for the surface it sits on.
    ramp: tuple[str, ...]


LIGHT = Theme(
    name="light",
    surface="#fcfcfb",
    text="#0b0b0b",
    secondary="#52514e",
    muted="#b9b8b2",
    series=("#2a78d6", "#eb6834", "#1baf7a"),
    ramp=("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"),
)

DARK = Theme(
    name="dark",
    surface="#1a1a19",
    text="#ffffff",
    secondary="#c3c2b7",
    muted="#4a4a46",
    series=("#3987e5", "#d95926", "#199e70"),
    ramp=("#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"),
)

THEMES = (LIGHT, DARK)


def ramp(theme: Theme) -> LinearSegmentedColormap:
    """The sequential ramp as a colormap, light-to-dark on its own surface."""
    return LinearSegmentedColormap.from_list(f"pcp-{theme.name}", theme.ramp)


def apply(theme: Theme) -> None:
    """Set the global style for one theme.

    Grid and axes are deliberately recessive: they are not the data.
    """
    mpl.rcParams.update(
        {
            "figure.facecolor": theme.surface,
            "axes.facecolor": theme.surface,
            "savefig.facecolor": theme.surface,
            "text.color": theme.text,
            "axes.labelcolor": theme.secondary,
            "axes.edgecolor": theme.muted,
            "xtick.color": theme.secondary,
            "ytick.color": theme.secondary,
            "grid.color": theme.muted,
            "grid.alpha": 0.4,
            "grid.linewidth": 0.6,
            "axes.titlesize": 11,
            "axes.titleweight": "semibold",
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 160,
        }
    )


def save(figure: plt.Figure, name: str, theme: Theme, *, raster: bool) -> Path:
    """Write one theme's version of a figure.

    Map figures are raster: a million points in SVG is a file nobody can open.
    Data charts stay vector, where they are sharp at any zoom and small.
    """
    OUTPUT.mkdir(parents=True, exist_ok=True)
    suffix = "png" if raster else "svg"
    path = OUTPUT / f"{name}-{theme.name}.{suffix}"
    figure.savefig(path, bbox_inches="tight", pad_inches=0.25)
    plt.close(figure)
    return path
