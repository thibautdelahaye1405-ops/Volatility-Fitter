"""Shared Matplotlib style for the LQD paper figure suite.

One restrained, colorblind-safe palette across all fourteen figures: the
first three categorical slots of the validated reference palette (blue =
model, orange = market data, aqua = comparator) plus neutral inks for
reference geometry.  The three-slot set passes the palette validator's
all-pairs CVD and normal-vision floors on a white surface (worst pair
deltaE 9.2 CVD / 24.0 normal); the aqua slot's sub-3:1 contrast is
relieved by direct labels wherever it appears.  Serif STIX text matches
the 11pt LaTeX article; the base font is 9pt at final size because every
figure is included at its natural width (6.3 in ~ \\textwidth, or 2.1 in
per panel of a three-panel row).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

FIG_DIR = Path(__file__).resolve().parents[2] / "figures"

PALETTE = {
    "model": "#2a78d6",  # slot 1 blue: LQD fits and model-derived objects
    "data": "#eb6834",   # slot 2 orange: quotes, haircut bands, observed
    "alt": "#1baf7a",    # slot 3 aqua: comparator series (always direct-labeled)
    "ink": "#1f2430",    # reference / target curves, emphasis text
    "muted": "#898781",  # de-emphasized geometry, callout text
    "grid": "#e1e0d9",   # hairline gridlines
}

# Figure sizes in inches for a 6.3 in text width.
ROW3 = (6.3, 2.30)      # one row of three labeled panels
ROW2 = (6.3, 2.70)      # one row of two labeled panels
ONE = (6.3, 3.10)       # a single full-width axis
GALLERY = (6.3, 3.60)   # the 2 x 4 SPY gallery
GRID22 = (6.3, 4.50)    # the 2 x 2 NVDA figure


def setup() -> None:
    """Install the paper-wide Matplotlib defaults (call once per process)."""
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
    """Save ``figures/<slug>.pdf`` and release the figure."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"{slug}.pdf"
    fig.savefig(path)
    plt.close(fig)
    return path


def panel(ax, tag: str, title: str) -> None:
    """Left-aligned per-panel title in the paper's '(a)  ...' convention."""
    ax.set_title(f"({tag})  {title}", loc="left", fontsize=9.0, pad=5.0)


def whiskers(ax, k, lo, hi, color=None, lw: float = 0.9, alpha: float = 0.85,
             label: str | None = None) -> None:
    """Draw per-quote haircut bands as thin vertical whiskers (never crosses)."""
    color = color or PALETTE["data"]
    k = np.asarray(k, dtype=float)
    segs = [((x, a), (x, b)) for x, a, b in zip(k, np.asarray(lo), np.asarray(hi))]
    ax.add_collection(
        LineCollection(segs, colors=color, linewidths=lw, alpha=alpha, zorder=3)
    )
    if label is not None:  # proxy artist so the whiskers can enter a legend
        ax.plot([], [], color=color, lw=lw, alpha=alpha, label=label)


def rms_note(ax, rms_bp: float, extra: str = "") -> None:
    """Annotate a gallery panel with its rms fit error in vol bp."""
    text = f"rms {rms_bp:.1f} bp"
    if extra:
        text += f"\n{extra}"
    ax.text(
        0.97, 0.95, text, transform=ax.transAxes, ha="right", va="top",
        fontsize=7.5, color=PALETTE["ink"],
    )


def callout(ax, text: str, xy, xytext, fontsize: float = 7.5) -> None:
    """A muted annotation arrow for the one thing the reader must notice."""
    ax.annotate(
        text, xy=xy, xytext=xytext,
        arrowprops={"arrowstyle": "->", "color": PALETTE["muted"], "lw": 0.9},
        fontsize=fontsize, color=PALETTE["muted"],
    )
