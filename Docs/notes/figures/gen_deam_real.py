"""Figures and macros for Note 05: the de-Americanization wedge on a REAL chain.

Uses the production CRR machinery (volfit.core.american) on the true-weekly
Massive capture (backend/tests/fixtures/lv_weekly_massive.json, SPY, as-of
2026-06-25), December-2026 expiry (~6 months out). Two populations, two
figures:

(1) STRESS exhibit (fig_deam_real.pdf): every two-sided put, including the
    deep in-the-money ones. Each mid is inverted two ways — naively through
    the analytic European Black formula (production's inversion, what a fitter
    that ignored early exercise would compute) and through the production
    American tree (volfit.core.american.deamericanize_batch). The wedge on ITM
    puts is the MODEL-IMPLIED IV effect of the early-exercise premium. These
    ITM puts are NOT what Vol-Fitter fits: production quote prep keeps only
    the OTM side (puts below F, calls above — volfit/api/quotes.py), so this
    panel is an economic stress illustration of what skipping de-Am would do
    to the discarded side, not the fitter's actual exposure.

(2) PRODUCTION-SELECTED population (fig_deam_real_selected.pdf): the quotes
    quote prep actually keeps — OTM puts below the forward, OTM calls above —
    with the same two-way inversion. This is the fit's actual de-Am exposure;
    its median/max macros are the numbers the note may quote as such.

Carry note: this delayed-tier capture's parity-implied rate is unphysical
(negative, clamped; see Note 06), so the carry is supplied: r = 4.3%
money-market, q = 1.2% SPY dividend yield (mid-2026), F = S e^{(r-q)t},
D = e^{-rt}. The note's captions and prose state this.

Outputs (next to this file):
  fig_deam_real.pdf           stress exhibit: every put, ITM wedge
  fig_deam_real_selected.pdf  production-selected OTM quotes' de-Am effect
  deam_real_tables.tex        \\input-able macros (both populations)
  deam_real_numbers.json      the same numbers, machine-readable

Run from the repo root with the project venv:
  .\\.venv\\Scripts\\python.exe Docs\\notes\\figures\\gen_deam_real.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))  # shared figure style (STYLE_GUIDE.md section 6)
REPO = OUT.parents[2]
sys.path.insert(0, str(REPO / "backend"))  # lv_benchmark fixture loader

from style import PALETTE, save, setup  # noqa: E402

from lv_benchmark import load_benchmark  # noqa: E402
from volfit.core.american import deamericanize_batch  # noqa: E402
from volfit.core.black import implied_total_variance  # noqa: E402

setup()
TEAL, BLUE, RUST, SLATE = (
    PALETTE["teal"], PALETTE["blue"], PALETTE["rust"], PALETTE["muted"],
)

FIXTURE = REPO / "backend" / "tests" / "fixtures" / "lv_weekly_massive.json"
EXPIRY = date(2026, 12, 18)  # ~6 months from the capture as-of
R, Q = 0.043, 0.012  # supplied carry (see module docstring / Note 06)


def naive_black_iv(is_call: np.ndarray, mids: np.ndarray, ks: np.ndarray,
                   f: float, d: float, t: float) -> np.ndarray:
    """The biased vols: invert AMERICAN market prices as if European, through
    the analytic Black formula in normalized forward units (production's
    inversion — volfit/api/quotes.py normalization + core.black)."""
    k = np.log(ks / f)
    shift = np.where(is_call, 0.0, 1.0 - np.exp(k))
    w = implied_total_variance(k, mids / (d * f) + shift)
    with np.errstate(invalid="ignore"):
        return np.sqrt(w / t)


def two_sided(snap, expiry, side=None):
    """Sorted two-sided quotes of one expiry; ``side`` filters 'C'/'P'."""
    qs = [x for x in snap.quotes_for(expiry)
          if x.mid is not None and x.ask is not None and x.bid and x.bid > 0
          and (side is None or x.call_put == side)]
    return sorted(qs, key=lambda x: x.strike)


def stress_puts_figure(snap, s, f, d, t):
    """Every put (incl. deep ITM): the wedge a European inversion would show."""
    puts = two_sided(snap, EXPIRY, side="P")
    ks = np.array([p.strike for p in puts], dtype=float)
    mids = np.array([p.mid for p in puts], dtype=float)
    keep = (ks >= 0.55 * s) & (ks <= 1.38 * s)
    ks, mids = ks[keep], mids[keep]
    is_call = np.zeros(ks.size, dtype=bool)

    deam = deamericanize_batch(is_call, mids, s, ks, t, R, Q)
    naive = naive_black_iv(is_call, mids, ks, f, d, t)
    ok = np.isfinite(deam) & np.isfinite(naive)
    ks, deam, naive = ks[ok], deam[ok], naive[ok]
    pct = 100.0 * ks / s
    bias_bp = 1e4 * (naive - deam)
    itm = pct > 100.0  # spot-ITM puts; production discards those at/above F
    med_itm = float(np.median(bias_bp[itm]))
    max_bias = float(bias_bp.max())

    fig, ax = plt.subplots(figsize=(6.9, 4.2))
    ax.fill_between(pct, 100 * deam, 100 * naive, where=pct >= 100.0,
                    color=RUST, alpha=0.10, lw=0)
    ax.plot(pct, 100 * naive, color=RUST, lw=1.8,
            label="American mid inverted as European (Black) — biased")
    ax.plot(pct, 100 * deam, color=TEAL, ls="--", lw=2.0,
            label="de-Americanized (CRR-inverted) — European-equivalent")
    ax.axvline(100.0, color=SLATE, ls=":", lw=1.1, alpha=0.8)
    ax.annotate("ATM", xy=(100.0, 0.02), xycoords=("data", "axes fraction"),
                xytext=(3, 0), textcoords="offset points", color=SLATE, fontsize=9)
    i = int(np.argmin(np.abs(pct - 124.0)))
    ax.annotate(
        "the wedge = model-implied IV effect of the EEP\n"
        "(ITM puts — nearly all discarded for OTM calls;\n"
        "median +%.0f bp, max +%.0f bp)" % (med_itm, max_bias),
        xy=(pct[i], 50 * (naive[i] + deam[i])), xytext=(-196, 40),
        textcoords="offset points", color=PALETTE["ink"], fontsize=9,
        arrowprops={"arrowstyle": "-", "color": SLATE, "lw": 0.9},
    )
    ax.set_xlabel("put strike (% of spot)")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout()
    save(fig, OUT / "fig_deam_real.pdf")
    return {"n_puts": int(ks.size), "n_itm": int(itm.sum()),
            "median_itm_bias_bp": med_itm, "max_bias_bp": max_bias,
            "max_bias_strike": float(ks[bias_bp.argmax()])}


def selected_figure(snap, s, f, d, t, itm_median_bp):
    """The quotes production actually fits: OTM puts below F, OTM calls above,
    after the tick floor and the Z_MAX = 4 sd wing filter of quote prep
    (volfit/api/quotes.py) — without them the deep wings production drops
    would dominate the picture with tick-quantum noise."""
    tick_floor = 3.0 * snap.tick_size if getattr(snap, "tick_size", None) else 0.0
    qs = [x for x in two_sided(snap, EXPIRY)
          if x.call_put == ("C" if x.strike >= f else "P") and x.mid > tick_floor]
    ks = np.array([x.strike for x in qs], dtype=float)
    mids = np.array([x.mid for x in qs], dtype=float)
    is_call = np.array([x.call_put == "C" for x in qs], dtype=bool)

    deam = deamericanize_batch(is_call, mids, s, ks, t, R, Q)
    naive = naive_black_iv(is_call, mids, ks, f, d, t)
    ok = np.isfinite(deam) & np.isfinite(naive)
    ks, is_call, deam, naive = ks[ok], is_call[ok], deam[ok], naive[ok]
    # Wing filter, as in production: ATM total variance from the de-Am'd mids,
    # then keep |k| <= 4 sqrt(w_atm).
    k_log = np.log(ks / f)
    w = deam**2 * t
    w_atm = float(np.interp(0.0, k_log, w))
    wing = np.abs(k_log) <= 4.0 * np.sqrt(w_atm)
    ks, is_call, deam, naive = ks[wing], is_call[wing], deam[wing], naive[wing]
    pct = 100.0 * ks / s
    bias_bp = 1e4 * (naive - deam)
    puts, calls = bias_bp[~is_call], bias_bp[is_call]

    fig, ax = plt.subplots(figsize=(6.9, 3.9))
    ax.plot(pct[~is_call], bias_bp[~is_call], "o", ms=4.5, color=TEAL,
            label="selected OTM puts (below $F$)")
    ax.plot(pct[is_call], bias_bp[is_call], "s", ms=4.0, color=BLUE,
            label="selected OTM calls (above $F$)")
    ax.axvline(100.0 * f / s, color=SLATE, ls=":", lw=1.1, alpha=0.8)
    ax.annotate("$F$", xy=(100.0 * f / s, 0.9), xycoords=("data", "axes fraction"),
                xytext=(3, 0), textcoords="offset points", color=SLATE, fontsize=9)
    ax.annotate(
        "the fitted population: median $|$effect$|$ %.1f bp, max %.0f bp\n"
        "(vs +%.0f bp median on the discarded ITM puts)"
        % (float(np.median(np.abs(bias_bp))), float(bias_bp.max()), itm_median_bp),
        xy=(0.03, 0.86), xycoords="axes fraction", color=PALETTE["ink"],
        fontsize=9,
    )
    ax.set_xlabel("strike (% of spot)")
    ax.set_ylabel("naive $-$ de-Am implied vol (vol bp)")
    ax.legend(frameon=False, loc="center left", fontsize=9)
    fig.tight_layout()
    save(fig, OUT / "fig_deam_real_selected.pdf")
    return {"n_selected": int(ks.size),
            "median_bp": float(np.median(bias_bp)),
            "abs_median_bp": float(np.median(np.abs(bias_bp))),
            "max_bp": float(bias_bp.max()),
            "put_median_bp": float(np.median(puts)) if puts.size else 0.0,
            "put_max_bp": float(puts.max()) if puts.size else 0.0,
            "call_median_bp": float(np.median(calls)) if calls.size else 0.0,
            "call_max_bp": float(calls.max()) if calls.size else 0.0}


def main() -> None:
    data, chains = load_benchmark(FIXTURE)
    ref = date.fromisoformat(data["as_of"])
    snap = chains["SPY"]
    s = float(snap.spot)
    t = (EXPIRY - ref).days / 365.0
    f = s * float(np.exp((R - Q) * t))
    d = float(np.exp(-R * t))

    stress = stress_puts_figure(snap, s, f, d, t)
    sel = selected_figure(snap, s, f, d, t, stress["median_itm_bias_bp"])

    lines = [
        "% Auto-generated by gen_deam_real.py — do not edit.",
        r"\newcommand{\deamrealmedianitm}{%.0f}" % stress["median_itm_bias_bp"],
        r"\newcommand{\deamrealmaxbias}{%.0f}" % stress["max_bias_bp"],
        r"\newcommand{\deamrealnputs}{%d}" % stress["n_puts"],
        r"\newcommand{\deamrealnitm}{%d}" % stress["n_itm"],
        r"\newcommand{\deamrealseln}{%d}" % sel["n_selected"],
        r"\newcommand{\deamrealselmedian}{%.1f}" % sel["median_bp"],
        r"\newcommand{\deamrealselabsmedian}{%.1f}" % sel["abs_median_bp"],
        r"\newcommand{\deamrealselmax}{%.0f}" % sel["max_bp"],
        r"\newcommand{\deamrealselputmedian}{%.0f}" % sel["put_median_bp"],
        r"\newcommand{\deamrealselputmax}{%.0f}" % sel["put_max_bp"],
        r"\newcommand{\deamrealselcallmedian}{%.1f}" % sel["call_median_bp"],
        r"\newcommand{\deamrealselcallmax}{%.1f}" % sel["call_max_bp"],
    ]
    (OUT / "deam_real_tables.tex").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    (OUT / "deam_real_numbers.json").write_text(json.dumps(
        {"stress_all_puts": stress, "production_selected": sel,
         "spot": s, "forward": f, "discount": d, "t_years": t,
         "expiry": EXPIRY.isoformat(), "as_of": ref.isoformat(),
         "r": R, "q": Q,
         "naive_leg": "analytic Black inversion (production normalization)"},
        indent=2), encoding="utf-8")
    print(f"SPY {EXPIRY} (as-of {ref}), spot {s:.2f}, F {f:.2f}, t={t:.3f}")
    print(f"stress puts: {stress['n_puts']} ({stress['n_itm']} ITM), "
          f"median ITM {stress['median_itm_bias_bp']:.0f} bp, "
          f"max {stress['max_bias_bp']:.0f} bp at K={stress['max_bias_strike']:.0f}")
    print(f"production-selected: {sel['n_selected']} quotes, "
          f"median {sel['median_bp']:.1f} bp (|.| {sel['abs_median_bp']:.1f}), "
          f"max {sel['max_bp']:.0f} bp "
          f"(puts {sel['put_median_bp']:.0f}/{sel['put_max_bp']:.0f}, "
          f"calls {sel['call_median_bp']:.1f}/{sel['call_max_bp']:.1f})")


if __name__ == "__main__":
    main()
