"""Static PNG fallbacks for hosts that do not render MCP Apps.

matplotlib (Agg, imported lazily so the server starts without it) draws the
same structured content the HTML apps consume: a heatmap trio per ticker for
the LV compare, the fit-vs-bands smile. Kept deliberately small (≈ 100 dpi)
because chat hosts show tool images collapsed and count them as tokens.
"""

from __future__ import annotations

import io
from typing import Any

DPI = 100


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight")
    _plt().close(fig)
    return buf.getvalue()


def lv_compare_png(structured: dict[str, Any]) -> bytes:
    """One row per ticker: affine LV, Dupire twin, difference (vol points)."""
    plt = _plt()
    panels = structured["tickers"]
    fig, axes = plt.subplots(len(panels), 3, figsize=(12, 3.4 * len(panels)), squeeze=False)
    for row, p in zip(axes, panels):
        x, t = p["xNodes"], p["tNodes"]
        extent = (x[0], x[-1], t[0], t[-1]) if x and t else None
        layers = [("Affine LV", p["affine"], "viridis", None),
                  ("Dupire twin", p["twin"], "viridis", None),
                  ("Affine − twin", p["diff"], "RdBu_r", "sym")]
        for ax, (title, z, cmap, mode) in zip(row, layers):
            if not z:
                ax.set_axis_off()
                ax.set_title(f"{p['ticker']} {title}: n/a")
                continue
            kw = {}
            if mode == "sym":
                m = max(abs(v) for r in z for v in r) or 1e-3
                kw = {"vmin": -m, "vmax": m}
            im = ax.imshow(z, origin="lower", aspect="auto", extent=extent, cmap=cmap, **kw)
            fig.colorbar(im, ax=ax, fraction=0.046)
            ax.set_title(f"{p['ticker']} {title}")
            ax.set_xlabel("K / F")
            ax.set_ylabel("T (y)")
    fig.suptitle(f"Local-Vol compare — {structured.get('tInterp')} twin", y=1.0)
    fig.tight_layout()
    return _png(fig)


def smile_png(sm: dict[str, Any]) -> bytes:
    """Fit curve vs bid/ask IV bands (+ prior / LV curves when present)."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    q = sm.get("quotes") or []
    if q:
        ks = [p["k"] for p in q]
        mids = [p["mid"] for p in q]
        lo = [p["mid"] - p["bid"] for p in q]
        hi = [p["ask"] - p["mid"] for p in q]
        ax.errorbar(ks, mids, yerr=[lo, hi], fmt="o", ms=3, color="#555", ecolor="#999", capsize=2, label="bid/ask")
    for key, style, label in (("fit", "-", sm.get("model") or "fit"), ("prior", "--", "prior"), ("lv", ":", "Local Vol")):
        c = sm.get(key)
        if c:
            ax.plot([p[0] for p in c], [p[1] for p in c], style, lw=1.6, label=label)
    d = sm.get("diagnostics") or {}
    ax.set_title(f"{sm['ticker']} {sm['expiry']} — rms {d.get('rmsBp')} bp, ATM {d.get('atmVol')}")
    ax.set_xlabel("k = ln(K/F)")
    ax.set_ylabel("implied vol")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return _png(fig)
