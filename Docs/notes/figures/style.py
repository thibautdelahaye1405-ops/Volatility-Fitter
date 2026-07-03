"""Shared plotting style for the Vol-Fitter technical-note figures.

Every generator in Docs/notes/figures/ calls ``setup()`` once at import time so
the whole series shares one typography, palette and export contract (see
Docs/notes/STYLE_GUIDE.md section 6). Figures are sized for the notes' 1-inch
margins: FULL (~6.5in) for single full-width figures, WIDE for annotated
one-row multi-panel figures, HALF for the rare side-by-side minipage pair.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

# One palette for the series: "ink" for text/zero-lines, "muted" for callouts
# and de-emphasized geometry, the rest are data colours. "rust" is reserved
# for observed/lit/error objects, "teal" for the model/posterior object.
PALETTE = {
    "ink": "#1f2937",
    "muted": "#64748b",
    "grid": "#d6dee8",
    "teal": "#0f766e",
    "blue": "#2563eb",
    "rust": "#b91c1c",
    "amber": "#b45309",
    "violet": "#7c3aed",
    "green": "#15803d",
}

# Figure widths in inches for a 6.5in text block.
FULL = (6.9, 3.9)   # one full-width figure
WIDE = (7.6, 3.7)   # full-width figure holding 2 labelled panels
HALF = (3.5, 3.0)   # one panel of a minipage pair


def setup() -> None:
    """Install the series-wide Matplotlib defaults (call once per generator)."""
    plt.rcParams.update(
        {
            "figure.figsize": FULL,
            "font.size": 11.5,
            "axes.titlesize": 12.5,
            "axes.labelsize": 11.5,
            "legend.fontsize": 9.5,
            "xtick.labelsize": 10.5,
            "ytick.labelsize": 10.5,
            "axes.grid": True,
            "grid.color": PALETTE["grid"],
            "grid.alpha": 0.55,
            "grid.linewidth": 0.7,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#94a3b8",
            "axes.labelcolor": PALETTE["ink"],
            "text.color": PALETTE["ink"],
            "xtick.color": PALETTE["ink"],
            "ytick.color": PALETTE["ink"],
            "lines.linewidth": 2.0,
            "lines.markersize": 6.0,
            "legend.frameon": False,
            "savefig.bbox": "tight",
            "savefig.dpi": 220,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save(fig, path: Path) -> None:
    """Save with the series export settings and release the figure."""
    fig.savefig(path)
    plt.close(fig)


def label_panel(ax, label: str) -> None:
    """Stamp a bold panel tag (A, B, ...) above the axes' top-left corner."""
    ax.text(
        -0.06,
        1.05,
        label,
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        va="bottom",
        ha="left",
    )


def callout(ax, text: str, xy, xytext, fontsize: float = 9.5) -> None:
    """A muted annotation arrow: the one thing the reader must see."""
    ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        arrowprops={"arrowstyle": "->", "color": PALETTE["muted"], "lw": 1.1},
        fontsize=fontsize,
        color=PALETTE["muted"],
    )
