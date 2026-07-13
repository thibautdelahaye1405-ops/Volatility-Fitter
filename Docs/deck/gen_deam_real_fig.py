"""Deck figure: de-Americanization bias on a REAL captured SPY chain.

Rev-6 replacement for the synthetic fig_deam_bias on the de-Am slide. Uses the
production CRR machinery (volfit.core.american) on the true-weekly Massive
capture (backend/tests/fixtures/lv_weekly_massive.json, SPY, as-of 2026-06-25):
for every put of one expiry, invert the observed American mid two ways —
naively through the analytic European Black formula (production's inversion,
what a fitter that ignores early exercise would compute) and properly through
the AMERICAN tree (the de-Americanized European-equivalent vol). The wedge on
in-the-money puts is the model-implied IV effect of the early-exercise
premium, on live market prices. Honesty note (Note 05): production fits the
OTM side only, so these ITM puts are the discarded twins of fitted OTM calls —
the chart is a stress exhibit, not the fitted population's exposure (that runs
a median |effect| of a few bp, tens in the put wing).

Carry note: this delayed-tier capture's parity-implied rate is unphysical
(negative, clamped), so the carry is supplied: r = 4.3% money-market,
q = 1.2% SPY dividend yield (mid-2026). The caption states this.

Output: Docs/deck/assets/fig/fig_deam_bias_real.png (also .pdf next to it).
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
sys.path.insert(0, str(REPO / "backend"))  # lv_benchmark fixture loader

from style import PALETTE, setup  # noqa: E402

from lv_benchmark import load_benchmark  # noqa: E402
from volfit.core.american import deamericanize_batch  # noqa: E402
from volfit.core.black import implied_total_variance  # noqa: E402

setup()
TEAL, RUST, SLATE = PALETTE["teal"], PALETTE["rust"], PALETTE["muted"]
OUT = REPO / "Docs" / "deck" / "assets" / "fig"

FIXTURE = REPO / "backend" / "tests" / "fixtures" / "lv_weekly_massive.json"
EXPIRY = date(2026, 12, 18)
R, Q = 0.043, 0.012  # supplied carry (see module docstring)


def naive_black_iv(mids: np.ndarray, s: float, ks: np.ndarray, t: float) -> np.ndarray:
    """The biased vols: invert AMERICAN put mids as if European through the
    analytic Black formula (production's inversion + normalization)."""
    f = s * float(np.exp((R - Q) * t))
    d = float(np.exp(-R * t))
    k = np.log(ks / f)
    w = implied_total_variance(k, mids / (d * f) + 1.0 - np.exp(k))
    with np.errstate(invalid="ignore"):
        return np.sqrt(w / t)


def main():
    data, chains = load_benchmark(FIXTURE)
    ref = date.fromisoformat(data["as_of"])
    snap = chains["SPY"]
    s = float(snap.spot)
    t = (EXPIRY - ref).days / 365.0

    puts = sorted(
        (x for x in snap.quotes_for(EXPIRY)
         if x.call_put == "P" and x.mid is not None and x.bid and x.bid > 0),
        key=lambda x: x.strike,
    )
    ks = np.array([p.strike for p in puts], dtype=float)
    mids = np.array([p.mid for p in puts], dtype=float)

    keep = (ks >= 0.55 * s) & (ks <= 1.38 * s)
    ks, mids = ks[keep], mids[keep]

    deam = deamericanize_batch(np.zeros(ks.size, dtype=bool), mids, s, ks, t, R, Q)
    naive = naive_black_iv(mids, s, ks, t)

    ok = np.isfinite(deam) & np.isfinite(naive)
    ks, deam, naive = ks[ok], deam[ok], naive[ok]
    pct = 100.0 * ks / s
    bias_bp = 1e4 * (naive - deam)
    itm_mask = pct > 100.0
    med_itm = float(np.median(bias_bp[itm_mask]))
    max_bias = float(bias_bp.max())

    fig, ax = plt.subplots(figsize=(7.4, 4.5))
    ax.fill_between(pct, 100 * deam, 100 * naive, where=pct >= 100.0,
                    color=RUST, alpha=0.10, lw=0)
    ax.plot(pct, 100 * naive, color=RUST, lw=1.8,
            label="American mid inverted as European — biased")
    ax.plot(pct, 100 * deam, color=TEAL, ls="--", lw=2.0,
            label="de-Americanized (CRR-inverted) — European-equivalent")
    ax.axvline(100.0, color=SLATE, ls=":", lw=1.1, alpha=0.8)
    ax.annotate("ATM", xy=(100.0, 0.02), xycoords=("data", "axes fraction"),
                xytext=(3, 0), textcoords="offset points", color=SLATE, fontsize=9)
    i = int(np.argmin(np.abs(pct - 124.0)))
    ax.annotate("the wedge = model-implied IV effect of the EEP\n"
                "(median ITM +%.0f bp, max +%.0f bp)" % (med_itm, max_bias),
                xy=(pct[i], 50 * (naive[i] + deam[i])), xytext=(-172, 46),
                textcoords="offset points", color=PALETTE["ink"], fontsize=9,
                arrowprops=dict(arrowstyle="-", color=SLATE, lw=0.9))

    ax.set_xlabel("put strike (% of spot)")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_deam_bias_real.png", dpi=200)
    fig.savefig(OUT / "fig_deam_bias_real.pdf")
    plt.close(fig)

    itm = pct > 100.0
    print(f"SPY {EXPIRY} (as-of {ref}), {ks.size} puts, spot {s:.2f}, t={t:.3f}")
    print(f"max bias {bias_bp.max():.0f} bp at K={ks[bias_bp.argmax()]:.0f} "
          f"({pct[bias_bp.argmax()]:.0f}% of spot)")
    print(f"median ITM-put bias {np.median(bias_bp[itm]):.0f} bp; "
          f"median OTM-put bias {np.median(bias_bp[~itm]):.1f} bp")


if __name__ == "__main__":
    main()
