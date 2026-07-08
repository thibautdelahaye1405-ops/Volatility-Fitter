"""Deck figure: fit-to-mid vs fit-to-band on a chain with noisy wing mids.

Rev-4 replacement for fig_obj_band_deck.png (slide 17). Uses the PRODUCTION
calibrator (volfit.models.lqd.calibrate.calibrate_slice) and the production
band objective (volfit.calib.band.resolve_band) on a synthetic chain built to
look like a real one: tight spreads near ATM, wide spreads in the wings, and
stale wing mids scattered anywhere inside their spread. The mid fit chases
those prints into kinks; the band fit stays a smooth smile because a clean
curve already sits inside every quoted spread.

Output: Docs/deck/assets/fig/fig_obj_band_deck.png (also .pdf next to it).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(r"C:\Users\thiba\vol-fitter")
sys.path.insert(0, str(REPO / "Docs" / "notes" / "figures"))  # notes' style.py

from style import PALETTE, setup  # noqa: E402

from volfit.calib.band import resolve_band  # noqa: E402
from volfit.models.lqd.calibrate import calibrate_slice  # noqa: E402
from volfit.models.svi_jw.svi import RawSVI  # noqa: E402

setup()
TEAL, RUST, SLATE, AMBER = (PALETTE["teal"], PALETTE["rust"],
                            PALETTE["muted"], PALETTE["amber"])
OUT = REPO / "Docs" / "deck" / "assets" / "fig"

# A realistic equity smile as ground truth (same reference slice the notes use).
RAW = RawSVI(a=0.0106, b=0.0729, rho=-0.5, m=0.0583, sigma=0.1010)
T = 0.5


def build_chain(rng: np.random.Generator):
    """Chain with dense ATM strikes, sparser wings; spreads and mid noise both
    grow into the wings (in IV terms), like a real single-name chain."""
    k = np.concatenate([
        np.linspace(-0.45, -0.14, 8),
        np.linspace(-0.11, 0.11, 12),
        np.linspace(0.14, 0.34, 7),
    ])
    iv_true = np.sqrt(RAW.total_variance(k) / T)
    # Half-spread in vol: ~40bp ATM, growing to ~350-450bp in the far wings.
    half = 0.004 + 0.09 * k**2 / (0.02 + np.abs(k)) + 0.05 * np.maximum(np.abs(k) - 0.12, 0.0)
    # Stale wing prints: mids drift anywhere inside the spread once |k| grows;
    # the tight ATM core stays honest. The drift is coherent over 2-3 strikes
    # (stale prints cluster by trade time), which is a wavelength the mid fit
    # CAN chase — so it visibly does.
    from scipy.ndimage import gaussian_filter1d
    wildness = np.clip((np.abs(k) - 0.06) / 0.16, 0.0, 1.0)
    u = gaussian_filter1d(rng.standard_normal(k.size), sigma=1.1)
    u = u / np.max(np.abs(u)) * 0.95
    mid = iv_true + wildness * u * half
    return k, mid, mid - half, mid + half, half, wildness


def fit(k, iv_mid, band=None):
    w = (iv_mid**2) * T
    # Production-default damping for BOTH fits: the only difference is the target.
    return calibrate_slice(k, w, T, n_order=12, reg_lambda=1e-6, band=band)


def pick_seed():
    """Search seeds for the draw where the mid fit visibly diverges from the
    band fit (max sup-distance between the two fitted curves, in vol pts)."""
    best, best_seed = -1.0, None
    kk = np.linspace(-0.44, 0.33, 200)
    for seed in range(1, 61):
        k, mid, bid, ask, half, wild = build_chain(np.random.default_rng(seed))
        try:
            rm = fit(k, mid)
            rb = fit(k, mid, band=resolve_band(bid, mid, ask, "bidask"))
        except Exception:
            continue
        gap = float(np.max(np.abs(100 * rm.slice.implied_vol(kk, T)
                                  - 100 * rb.slice.implied_vol(kk, T))))
        if gap > best:
            best, best_seed = gap, seed
    print(f"seed {best_seed}: max fit gap {best:.2f} vol pts")
    return best_seed


def main():
    rng = np.random.default_rng(pick_seed())
    k, mid, bid, ask, half, wild = build_chain(rng)

    res_mid = fit(k, mid)
    band = resolve_band(bid, mid, ask, "bidask")
    res_band = fit(k, mid, band=band)

    kk = np.linspace(k[0] - 0.015, k[-1] + 0.015, 400)
    v_mid = 100 * res_mid.slice.implied_vol(kk, T)
    v_band = 100 * res_band.slice.implied_vol(kk, T)

    fig, ax = plt.subplots(figsize=(7.4, 4.5))
    ax.fill_between(k, 100 * bid, 100 * ask, color=AMBER, alpha=0.16, lw=0,
                    label="bid–ask band")
    ax.plot(k, 100 * bid, color=AMBER, lw=0.9, alpha=0.55)
    ax.plot(k, 100 * ask, color=AMBER, lw=0.9, alpha=0.55)

    honest = wild < 0.35
    ax.plot(k[honest], 100 * mid[honest], "o", ms=3.6, color=SLATE, label="mid (tight spread)")
    ax.plot(k[~honest], 100 * mid[~honest], "D", ms=4.6, color=RUST, mfc="none",
            mew=1.4, label="mid (stale print in a wide spread)")

    ax.plot(kk, v_mid, color=RUST, ls="--", lw=1.7, label="fit to mids — chases the prints")
    ax.plot(kk, v_band, color=TEAL, lw=2.2, label="fit to the band — smooth smile inside every spread")

    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "fig_obj_band_deck.png", dpi=200)
    fig.savefig(OUT / "fig_obj_band_deck.pdf")
    plt.close(fig)

    def roughness(v):
        return float(np.sum(np.abs(np.diff(v, 2))))

    print(f"roughness mid {roughness(v_mid):.2f} vs band {roughness(v_band):.2f}")
    rms_mid = float(np.sqrt(np.mean((100 * res_mid.slice.implied_vol(k, T) - 100 * mid) ** 2)))
    rms_band = float(np.sqrt(np.mean((100 * res_band.slice.implied_vol(k, T) - 100 * mid) ** 2)))
    inb = np.mean((res_band.slice.implied_vol(k, T) >= bid) & (res_band.slice.implied_vol(k, T) <= ask))
    print(f"mid-fit RMS to mids {rms_mid:.2f} vol pts; band-fit {rms_band:.2f}; band fit in-band {100*inb:.0f}%")


if __name__ == "__main__":
    main()
