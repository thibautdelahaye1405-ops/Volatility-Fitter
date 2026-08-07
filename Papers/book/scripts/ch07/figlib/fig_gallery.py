"""Figure 7.7: what de-Americanization is worth, on the population that counts."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import data7  # first: extends sys.path to the ch03/ch06 figure libraries
import data3  # noqa: E402
import figstyle
import tree
from figstyle import PALETTE
from macros import STORE, num


def _wedge(node, K, mids, is_call, n: int = tree.N_BATCH):
    """(naive - deam) implied-vol wedge in vol bp, NaN where either fails."""
    S, t, F = node.spot, node.t, node.forward
    q = data7.carry_yield(F, S, t)
    D = float(np.exp(-data7.R_CONV * t))
    sig_star = tree.deamericanize_batch(mids, is_call, K, S, t,
                                        data7.R_CONV, q, n=n)
    sig_naive = tree.implied_vol_black(mids, is_call, K, F, D, t)
    return 1e4 * (sig_naive - sig_star), sig_star


def fig_deam_gallery() -> str:
    nodes = data3.nodes("SPY")
    run_node = data7.running_node()

    # ---- per-expiry fitted-population wedges
    per_exp = []
    dec = None
    for node in nodes:
        K, mids, is_call = data7.otm_population(node.ticker, node.expiry)
        wedge, sig_star = _wedge(node, K, mids, is_call)
        ok = np.isfinite(wedge)
        entry = {
            "t": node.t, "expiry": node.expiry, "n": int(ok.sum()),
            "med": float(np.median(np.abs(wedge[ok]))),
            "max": float(np.max(np.abs(wedge[ok]))),
        }
        per_exp.append(entry)
        if (node.ticker, node.expiry) == data7.RUNNING:
            dec = (K, wedge, is_call, ok, sig_star, mids)

    # ---- the running node's discarded ITM puts (the stress population)
    K_itm, p_itm = data7.itm_puts(*data7.RUNNING)
    wedge_itm, _ = _wedge(run_node, K_itm, p_itm,
                          np.zeros(K_itm.size, dtype=bool))
    ok_itm = np.isfinite(wedge_itm)
    n_dead = int((~ok_itm).sum())

    # ---- depth sensitivity on the running node (the contract table row)
    K, mids, is_call = data7.otm_population(*data7.RUNNING)
    _, sig_256 = _wedge(run_node, K, mids, is_call, n=256)
    _, sig_128 = _wedge(run_node, K, mids, is_call, n=128)
    both = np.isfinite(sig_256) & np.isfinite(sig_128)
    depth_bp = 1e4 * np.abs(sig_256[both] - sig_128[both])

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # ---- (a) the running node, quote by quote
    K_dec, wedge_dec, is_call_dec, ok_dec, _, _ = dec
    k_dec = np.log(K_dec / run_node.forward)
    puts = ok_dec & ~is_call_dec
    calls = ok_dec & is_call_dec
    ax_a.plot(k_dec[puts], wedge_dec[puts], ".", color=PALETTE["data"],
              ms=3.6, zorder=4, label="fitted puts ($K<F$)")
    ax_a.plot(k_dec[calls], wedge_dec[calls], ".", color=PALETTE["model"],
              ms=3.6, zorder=4, label="fitted calls ($K\\geq F$)")
    ax_a.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_a.set_xlabel("log-moneyness $k=\\log(K/F)$")
    ax_a.set_ylabel("naive $-$ de-Americanized (vol bp)")
    ax_a.legend(loc="upper right", fontsize=7.2)
    figstyle.panel(ax_a, "a", "the running node's fitted quotes")

    # ---- (b) the gallery: medians and maxima against maturity
    ts = np.array([e["t"] for e in per_exp])
    med = np.array([e["med"] for e in per_exp])
    mx = np.array([e["max"] for e in per_exp])
    ax_b.plot(ts, med, "o-", color=PALETTE["model"], ms=4.2, lw=1.1,
              label="median $|\\cdot|$, fitted quotes")
    ax_b.plot(ts, mx, "o--", color=PALETTE["model"], ms=4.2, lw=0.9,
              mfc="white", label="worst quote, fitted")
    ax_b.plot([run_node.t], [float(np.median(np.abs(wedge_itm[ok_itm])))],
              "s", color=PALETTE["data"], ms=5.0, zorder=5,
              label="median, discarded ITM puts")
    ax_b.set_xscale("log")
    ax_b.set_yscale("log")
    ax_b.set_xlabel("maturity $t$ (years, log)")
    ax_b.set_ylabel("absolute wedge (vol bp, log)")
    ax_b.legend(loc="upper left", fontsize=6.8)
    figstyle.panel(ax_b, "b", "eight SPY expiries: fitted vs discarded")

    figstyle.save(fig, "fig_deam_gallery")

    dec_entry = next(e for e in per_exp if e["expiry"] == data7.RUNNING[1])
    put_w = wedge_dec[puts]
    call_w = wedge_dec[calls]
    STORE.add("gallery", "DeamGalSelN", str(dec_entry["n"]),
              "fitted quotes on the running node (inverted both ways)")
    STORE.add("gallery", "DeamGalSelMedianBp", num(dec_entry["med"], 1),
              "running node: median |wedge| on fitted quotes (vol bp)")
    STORE.add("gallery", "DeamGalSelMaxBp", num(dec_entry["max"], 0),
              "running node: worst fitted-quote wedge (vol bp)")
    STORE.add("gallery", "DeamGalSelPutMedianBp",
              num(float(np.median(put_w)), 1),
              "running node: median wedge, fitted puts (vol bp)")
    STORE.add("gallery", "DeamGalSelCallMedianBp",
              num(float(np.median(call_w)), 1),
              "running node: median wedge, fitted calls (vol bp)")
    STORE.add("gallery", "DeamGalItmN", str(int(ok_itm.sum())),
              "discarded ITM puts that still invert (running node)")
    STORE.add("gallery", "DeamGalItmDead", str(n_dead),
              "discarded ITM puts on the intrinsic plateau (no inversion)")
    STORE.add("gallery", "DeamGalItmMedianBp",
              num(float(np.median(np.abs(wedge_itm[ok_itm]))), 0),
              "running node: median |wedge| on discarded ITM puts (vol bp)")
    STORE.add("gallery", "DeamGalItmMaxBp",
              num(float(np.max(np.abs(wedge_itm[ok_itm]))), 0),
              "running node: worst discarded-ITM-put wedge (vol bp)")
    STORE.add("gallery", "DeamGalWorstMedianBp",
              num(float(np.max(med)), 1),
              "largest per-expiry fitted median across the gallery (vol bp)")
    STORE.add("gallery", "DeamGalWorstMaxBp", num(float(np.max(mx)), 0),
              "largest single fitted-quote wedge across the gallery (vol bp)")
    STORE.add("gallery", "DeamGalShortMedianBp", num(med[0], 2),
              "shortest expiry's fitted median wedge (vol bp)")
    STORE.add("table", "DeamTblDepthMedianBp",
              num(float(np.median(depth_bp)), 1),
              "median |sigma*| shift, tree depth 256 vs 128, running node"
              " fitted quotes (vol bp)")
    STORE.add("table", "DeamTblDepthMaxBp",
              num(float(np.max(depth_bp)), 0),
              "worst such shift (vol bp)")
    return (f"dec med {dec_entry['med']:.1f} bp max {dec_entry['max']:.0f}, "
            f"itm med {np.median(np.abs(wedge_itm[ok_itm])):.0f} bp, "
            f"depth {np.median(depth_bp):.1f}/{np.max(depth_bp):.0f} bp")
