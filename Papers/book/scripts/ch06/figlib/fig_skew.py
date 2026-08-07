"""Figure 6.6: a forward error read back through Black -- the ATM gap and
the fake skew, measured on the real running node's fitted smile."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import brentq
from scipy.stats import norm

import data6
import figstyle
from figstyle import PALETTE
from macros import STORE, num

BUMP_BP = 10.0  # the imposed forward error (bp of F)


def _norm_black(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Chapter 2's normalized Black call B(k, w) = Phi(d+) - e^k Phi(d-)."""
    sw = np.sqrt(w)
    d_plus = -k / sw + 0.5 * sw
    return norm.cdf(d_plus) - np.exp(k) * norm.cdf(d_plus - sw)


def _profile(k: np.ndarray, w: np.ndarray, tau: float) -> tuple[np.ndarray, np.ndarray]:
    """d sigma / d log F at fixed price, call side and put side (per unit)."""
    sw = np.sqrt(w)
    d_plus = -k / sw + 0.5 * sw
    call = -norm.cdf(d_plus) / (norm.pdf(d_plus) * np.sqrt(tau))
    put = norm.cdf(-d_plus) / (norm.pdf(d_plus) * np.sqrt(tau))
    return call, put


def _reimply(k: float, w: float, delta: float, side: str, tau: float) -> float:
    """Re-implied vol of one OTM quote when the forward is misread by delta.

    The dollar price stays fixed; the modeler prices it at F' = F e^delta,
    so the strike's log-moneyness becomes k' = k - delta and the normalizer
    D F changes by e^delta.  Solve for the new total variance w'.
    """
    kp = k - delta
    if side == "C":
        target = np.exp(-delta) * _norm_black(np.array([k]), np.array([w]))[0]
        f = lambda wp: _norm_black(np.array([kp]), np.array([wp]))[0] - target
    else:  # normalized put P = B + e^k - 1
        target = np.exp(-delta) * (
            _norm_black(np.array([k]), np.array([w]))[0] + np.exp(k) - 1.0
        )
        f = lambda wp: (_norm_black(np.array([kp]), np.array([wp]))[0]
                        + np.exp(kp) - 1.0) - target
    return brentq(f, 1e-10, 4.0 * w + 0.5, xtol=1e-14)


def fig_fwd_skew() -> str:
    import fits  # Chapter 3's figlib (on sys.path via data6)

    node = data6.running_node()
    tau = node.t  # the book's clocks coincide until Chapter 8
    slice_ = fits.rebuild_stored_lqd(node)

    span = (float(node.k.min()), float(node.k.max()))
    k_put = np.linspace(span[0], -1e-4, 300)
    k_call = np.linspace(1e-4, span[1], 300)
    w_put = np.asarray(slice_.implied_vol(k_put, tau)) ** 2 * tau
    w_call = np.asarray(slice_.implied_vol(k_call, tau)) ** 2 * tau

    delta = BUMP_BP * 1e-4
    call_prof = _profile(k_call, w_call, tau)[0]
    put_prof = _profile(k_put, w_put, tau)[1]

    # Measured: re-imply every OTM quote at the bumped forward.
    d_put = np.array([
        (np.sqrt(_reimply(k, w, delta, "P", tau) / tau) - np.sqrt(w / tau))
        for k, w in zip(k_put, w_put)
    ])
    d_call = np.array([
        (np.sqrt(_reimply(k, w, delta, "C", tau) / tau) - np.sqrt(w / tau))
        for k, w in zip(k_call, w_call)
    ])

    # ATM gap per 10 bp of forward error (put-side limit minus call-side).
    gap_bp = 1e4 * float(d_put[-1] - d_call[0])
    at_put10 = 1e4 * float(np.interp(-0.10, k_put, d_put))
    at_call10 = 1e4 * float(np.interp(0.10, k_call, d_call))
    naive_gap = gap_bp * float(STORE.value("FwdLineGapBp")) / BUMP_BP

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the closed-form profile, per 10 bp of forward error.
    scale = delta * 1e4  # vol bp per BUMP_BP of forward error
    ax_a.plot(k_call, scale * call_prof, color=PALETTE["model"], lw=1.3,
              label="call side")
    ax_a.plot(k_put, scale * put_prof, color=PALETTE["alt"], lw=1.3,
              label="put side")
    ax_a.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    ax_a.set_xlabel("log-moneyness $k$")
    ax_a.set_ylabel(f"vol move per {BUMP_BP:.0f} bp of $F$ (vol bp)")
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "the closed-form profile, side by side")

    # (b) the OTM composite smile, re-implied at the bumped forward.
    ax_b.plot(k_put, 1e4 * d_put, color=PALETTE["data"], lw=1.3,
              label="re-implied minus true")
    ax_b.plot(k_call, 1e4 * d_call, color=PALETTE["data"], lw=1.3)
    ax_b.plot(k_put, scale * put_prof, color=PALETTE["ink"], lw=0.8, ls=":",
              label="linearized (panel a)")
    ax_b.plot(k_call, scale * call_prof, color=PALETTE["ink"], lw=0.8, ls=":")
    ax_b.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    figstyle.callout(ax_b, f"ATM gap {gap_bp:.0f} vol bp",
                     (0.004, 0.0), (0.06, 0.30 * gap_bp))
    ax_b.set_xlabel("log-moneyness $k$")
    ax_b.set_ylabel("IV change (vol bp)")
    ax_b.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "what the desk sees: a gap plus a skew move")

    figstyle.save(fig, "fig_fwd_skew")

    STORE.add("skew", "FwdSkewBumpBp", num(BUMP_BP, 0),
              "imposed forward error (bp of F)")
    STORE.add("skew", "FwdSkewGapBp", num(gap_bp, 0),
              "ATM put-call IV gap per 10 bp of forward error (vol bp)")
    STORE.add("skew", "FwdSkewPutTenBp", num(at_put10, 0),
              "IV change at k = -0.10, put side (vol bp)")
    STORE.add("skew", "FwdSkewCallTenBp", num(abs(at_call10), 0),
              "IV change magnitude at k = +0.10, call side (vol bp)")
    STORE.add("skew", "FwdSkewNaiveGapBp", num(abs(naive_gap), 0),
              "ATM gap the naive Section-6.2 forward would imprint (vol bp)")
    return (f"gap {gap_bp:.0f} bp per {BUMP_BP:.0f} bp; naive-forward gap "
            f"{naive_gap:.0f} bp")
