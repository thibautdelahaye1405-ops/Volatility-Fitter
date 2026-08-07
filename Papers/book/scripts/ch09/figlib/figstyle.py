"""Shared Matplotlib style for the book's Chapter 9 figure suite.

Identical conventions to Chapters 2-8 (scripts/ch08/figlib/figstyle.py): the
same restrained colorblind-safe palette, serif STIX text at 9 pt, and the
'(a)  ...' left-aligned panel titles.  Chapter 9 keeps today's observed
smile in the data orange and assigns one fixed color per stickiness regime:
sticky-moneyness in the model blue, sticky-strike in aqua, sticky-local-vol
in violet; reference geometry (truth reprices, guide lines) in ink/greys.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

FIG_DIR = Path(__file__).resolve().parents[3] / "figures" / "ch09"

PALETTE = {
    "model": "#2a78d6",  # sticky-moneyness (R = 0)
    "data": "#eb6834",   # today's observed / fitted smile
    "alt": "#1baf7a",    # sticky-strike (R = 1)
    "third": "#8a5cd6",  # sticky-local-vol (R = 2)
    "ink": "#1f2430",    # reference / truth, emphasis text
    "muted": "#898781",  # de-emphasized geometry, callout text
    "grid": "#e1e0d9",   # hairline gridlines
    "band": "#dfe7f2",   # shaded bands
    "mask": "#d8d6cf",   # out-of-scope cells
}

# One fixed color per regime, used by every figure in the chapter.
REGIME_COLORS = {0.0: PALETTE["model"], 1.0: PALETTE["alt"], 2.0: PALETTE["third"]}
REGIME_NAMES = {0.0: "sticky-moneyness", 1.0: "sticky-strike",
                2.0: "sticky-local-vol"}

# Figure sizes in inches for a 6.3 in text width.
ROW3 = (6.3, 2.30)      # one row of three labeled panels
ROW2 = (6.3, 2.70)      # one row of two labeled panels
ONE = (6.3, 3.10)       # a single full-width axis


def setup() -> None:
    """Install the book-wide Matplotlib defaults (call once per process)."""
    plt.rcParams.update(
        {
            "font.family": "STIXGeneral",
            "mathtext.fontset": "stix",
            "font.size": 9.0,
            "axes.titlesize": 9.0,
            "axes.labelsize": 9.0,
            "legend.fontsize": 8.0,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "axes.grid": True,
            "grid.color": PALETTE["grid"],
            "grid.alpha": 0.9,
            "grid.linewidth": 0.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#b9b7b0",
            "axes.linewidth": 0.7,
            "axes.labelcolor": PALETTE["ink"],
            "text.color": PALETTE["ink"],
            "xtick.color": PALETTE["ink"],
            "ytick.color": PALETTE["ink"],
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "lines.linewidth": 1.4,
            "lines.markersize": 4.0,
            "legend.frameon": False,
            "legend.handlelength": 1.6,
            "figure.constrained_layout.use": True,
            "savefig.bbox": "tight",
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
        }
    )


def save(fig, slug: str) -> Path:
    """Save ``figures/ch09/<slug>.pdf`` (plus an optional PNG preview)."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"{slug}.pdf"
    fig.savefig(path)
    png_dir = os.environ.get("CH09_PNG_DIR")
    if png_dir:
        Path(png_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(png_dir) / f"{slug}.png", dpi=150)
    plt.close(fig)
    return path


def panel(ax, tag: str, title: str) -> None:
    """Left-aligned per-panel title in the book's '(a)  ...' convention."""
    ax.set_title(f"({tag})  {title}", loc="left", fontsize=9.0, pad=5.0)


def whiskers(ax, x, lo, hi, color=None, lw: float = 0.9, alpha: float = 0.85,
             label: str | None = None) -> None:
    """Per-point intervals as thin vertical whiskers (never crosses)."""
    color = color or PALETTE["data"]
    x = np.asarray(x, dtype=float)
    segs = [((xi, a), (xi, b)) for xi, a, b in zip(x, np.asarray(lo), np.asarray(hi))]
    ax.add_collection(
        LineCollection(segs, colors=color, linewidths=lw, alpha=alpha, zorder=3)
    )
    if label is not None:
        ax.plot([], [], color=color, lw=lw, alpha=alpha, label=label)


def callout(ax, text: str, xy, xytext, fontsize: float = 7.5) -> None:
    """A muted annotation arrow for the one thing the reader must notice."""
    ax.annotate(
        text, xy=xy, xytext=xytext,
        arrowprops={"arrowstyle": "->", "color": PALETTE["muted"], "lw": 0.9},
        fontsize=fontsize, color=PALETTE["muted"],
    )
