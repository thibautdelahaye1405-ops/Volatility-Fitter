"""Deck figure: the R3xR6 ablation on ONE REAL census node — chart == panel.

Supersedes gen_siv_g_deck.py (synthetic fence demo): its clean-chain numbers
(fence for 10 bp) sat next to the ablation panel's census medians (fence
alone = 749 bp) and read as a contradiction. This figure re-fits one REAL
arb-prone node from the actual R3xR6 ablation census (backtest results
spike_aug2024_ablation_arb.json, 38 arb-prone nodes) in all four cells, so
the slide's case-file numbers and its chart are the SAME experiment:

    EFA, as-of 2024-07-29 (Aug-2024 vol spike), expiry 2024-08-09 (11d)
    neither  75 bp  g -116   |  R3 (de-Am repair)  18 bp  g -12
    R6 (fence) 726 bp g -0.02 (arb-free, fights corrupted inputs)
    both     34 bp  g -0.000 (arb-free AND tight)

Node chosen as the closest to the census medians (92/25/749/225 bp) with
both fence cells clean. Uses the ablation harness's own helpers, so the
numbers reproduce the stored census rows.

Output: Docs/deck/assets/fig/fig_siv_ablation_deck.png (also .pdf).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(r"C:\Users\thiba\vol-fitter")
sys.path.insert(0, str(REPO / "Docs" / "notes" / "figures"))  # notes' style.py
sys.path.insert(0, str(REPO / "backend"))  # backtest package

from style import PALETTE, setup  # noqa: E402

from backtest.ablation_arb import (  # noqa: E402
    _CONFIGS, _ext_grid, _fit, _prepared, _rms_bp,
)
from backtest.replay import list_fixtures, load_fixture, state_for_day  # noqa: E402
from volfit.calib.weights import resolve_weights  # noqa: E402

setup()
TEAL, RUST, SLATE, AMBER, VIOLET = (PALETTE["teal"], PALETTE["rust"],
                                    PALETTE["muted"], PALETTE["amber"],
                                    PALETTE["violet"])
OUT = REPO / "Docs" / "deck" / "assets" / "fig"

REGIME, ASSET = "spike_aug2024", "EFA"
AS_OF, EXPIRY = date(2024, 7, 29), date(2024, 8, 9)

_STYLE = {  # per-cell curve styling + legend naming
    "neither": dict(color=RUST, lw=1.9, ls="-", label="neither"),
    "R3": dict(color=AMBER, lw=1.6, ls="-", label="de-Am repair alone"),
    "R6": dict(color=VIOLET, lw=1.6, ls=":", label="fence alone"),
    "both": dict(color=TEAL, lw=2.2, ls="--", label="both (production)"),
}


def main():
    fixture = next(f for f in map(load_fixture, list_fixtures(regime=REGIME))
                   if f.asset == ASSET and f.as_of == AS_OF)
    state = state_for_day([fixture])

    prep = {r3: _prepared(state, ASSET, EXPIRY, r3) for r3 in (False, True)}
    base = prep[False]
    w_atm = float(np.interp(0.0, base.k, base.w_mid))
    grid = _ext_grid(base.k, w_atm)

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.axvspan(float(base.k.min()), float(base.k.max()),
               color=SLATE, alpha=0.10, lw=0)
    ax.axhline(0, color="black", lw=0.9)

    for label, r3, r6 in _CONFIGS:
        prepared = prep[r3]
        weights = resolve_weights("equal", prepared.k, prepared.w_mid)
        slice_ = _fit(prepared, 2, r6, weights)
        g = np.asarray(slice_.gatheral_g(grid), float)
        rms = _rms_bp(slice_, prepared.k, prepared.w_mid, prepared.tau, weights)
        min_g = float(np.nanmin(g))
        st = dict(_STYLE[label])
        arb = ("arb-free" if min_g > -0.05
               else f"worst g {min_g:.0f}" if min_g < -1 else f"worst g {min_g:.2f}")
        st["label"] = f"{st['label']} — {arb}, fit {rms:.0f} bp"
        ax.plot(grid, g, **st)
        print(f"{label:<8} rms {rms:8.1f} bp   min_g {min_g:10.3f}")

    ax.set_yscale("symlog", linthresh=1.0)
    ax.set_ylim(-300, 30)
    ax.set_yticks([-100, -10, -1, 0, 1, 10])
    ax.set_yticklabels(["−100", "−10", "−1", "0", "1", "10"])
    ax.annotate("quoted strikes", xy=(0.5 * float(base.k.min() + base.k.max()), 0.97),
                xycoords=("data", "axes fraction"), ha="center",
                color=SLATE, fontsize=9)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"Durrleman $g(k)$  (symlog)")
    ax.legend(frameon=False, loc="lower right", fontsize=8.6)
    fig.tight_layout()
    fig.savefig(OUT / "fig_siv_ablation_deck.png", dpi=200)
    fig.savefig(OUT / "fig_siv_ablation_deck.pdf")
    plt.close(fig)
    print(f"node: {ASSET} as-of {AS_OF} expiry {EXPIRY} "
          f"({(EXPIRY - AS_OF).days}d), {base.k.size} quotes")


if __name__ == "__main__":
    main()
