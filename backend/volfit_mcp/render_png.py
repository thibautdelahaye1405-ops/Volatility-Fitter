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


def _bands(ax, q: list[dict[str, Any]]) -> None:
    """The bid/ask IV bands as error bars around the mids."""
    ks = [p["k"] for p in q]
    mids = [p["mid"] for p in q]
    lo = [p["mid"] - p["bid"] for p in q]
    hi = [p["ask"] - p["mid"] for p in q]
    ax.errorbar(ks, mids, yerr=[lo, hi], fmt="o", ms=3, color="#555", ecolor="#999", capsize=2, label="bid/ask")


def _frame_quoted_range(ax, q: list[dict[str, Any]]) -> None:
    """Frame the quoted range (the model wings run far beyond it)."""
    lo, hi = min(p["k"] for p in q), max(p["k"] for p in q)
    pad = max(0.25 * (hi - lo), 0.02)
    ax.set_xlim(lo - pad, hi + pad)
    ys = [p["bid"] for p in q] + [p["ask"] for p in q]
    ax.set_ylim(max(0.0, min(ys) - 0.02), max(ys) + 0.02)


def _finish_smile(fig, ax, q: list[dict[str, Any]]) -> bytes:
    if q:
        _frame_quoted_range(ax, q)
    ax.set_xlabel("k = ln(K/F)")
    ax.set_ylabel("implied vol")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return _png(fig)


def smile_png(sm: dict[str, Any]) -> bytes:
    """Fit curve vs bid/ask IV bands (+ prior / LV curves when present)."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    q = sm.get("quotes") or []
    if q:
        _bands(ax, q)
    for key, style, label in (("fit", "-", sm.get("model") or "fit"), ("prior", "--", "prior"), ("lv", ":", "Local Vol")):
        c = sm.get(key)
        if c:
            ax.plot([p[0] for p in c], [p[1] for p in c], style, lw=1.6, label=label)
    d = sm.get("diagnostics") or {}
    ax.set_title(f"{sm['ticker']} {sm['expiry']} — rms {d.get('rmsBp')} bp, ATM {d.get('atmVol')}")
    return _finish_smile(fig, ax, q)


def series_frame_png(doc: dict[str, Any]) -> bytes:
    """One series frame: the bid/ask bands and every lane's smile for the
    shown expiry (``tools_series_frame`` structured content)."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    sh, f = doc.get("shown") or {}, doc.get("frame") or {}
    q = sh.get("quotes") or []
    if q:
        _bands(ax, q)
    names = doc.get("laneNames") or {}
    for lid in doc.get("laneOrder") or []:
        c = (sh.get("curves") or {}).get(lid)
        if c and c.get("k"):
            rms = f" ({c['rmsBp']} bp)" if c.get("rmsBp") is not None else ""
            ax.plot(c["k"], c["iv"], "-", lw=1.6, label=f"{names.get(lid, lid)}{rms}")
    ax.set_title(f"{doc.get('name')} — frame {f.get('idx', 0) + 1}/{doc.get('nFrames')} {f.get('ts', '')} · {sh.get('expiry')}")
    return _finish_smile(fig, ax, q)


def vol_surface_png(sf: dict[str, Any]) -> bytes:
    """Heatmap of sigma(k, T) with the ATM ridge marked."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.4))
    k, t = sf["k"], sf["t"]
    z = [[100 * v if v is not None else float("nan") for v in row] for row in sf["vol"]]
    im = ax.imshow(z, origin="lower", aspect="auto", extent=(k[0], k[-1], t[0], t[-1]), cmap="viridis")
    fig.colorbar(im, ax=ax, fraction=0.046, label="implied vol (%)")
    ax.plot([0.0] * len(t), t, "w--", lw=1, label="ATM")
    for ti, c in zip(t, sf.get("crop") or []):
        if c:
            ax.plot([c[0]["lo"], c[0]["hi"]], [ti, ti], "w-", lw=0.8, alpha=0.6)
    ax.set_title(f"{sf['ticker']} implied-vol surface")
    ax.set_xlabel("k = ln(K/F)")
    ax.set_ylabel("T (y)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    return _png(fig)


def term_png(tm: dict[str, Any]) -> bytes:
    """Two panels: ATM / var-swap vol vs t, total variance vs t (+ events)."""
    plt = _plt()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    pts, cv = tm["points"], tm["curve"]
    tt = [p["t"] for p in pts]
    a1.plot(cv["t"], [100 * v for v in cv["vol"]], "-", color="#2563eb", lw=1.5, label="interpolated")
    a1.plot(tt, [100 * p["atmVol"] for p in pts], "o", color="#2563eb", ms=4, label="ATM vol")
    a1.plot(tt, [100 * p["varSwapVol"] for p in pts], "s", color="#f59e0b", ms=4, label="var-swap vol")
    if any(p.get("priorVol") is not None for p in pts):
        a1.plot(tt, [100 * (p["priorVol"] or float("nan")) for p in pts], ":", color="#9333ea", label="prior")
    a2.plot(cv["t"], cv["w"], "-", color="#2563eb", lw=1.5, label="w(t)")
    a2.plot(tt, [p["w0"] for p in pts], "o", color="#2563eb", ms=4, label="w0 per expiry")
    for e in tm.get("events") or []:
        for ax in (a1, a2):
            ax.axvline(e["time"], color="#dc2626", lw=0.8, alpha=0.6)
    for ax, ylabel in ((a1, "vol (%)"), (a2, "total variance")):
        ax.set_xlabel("t (y)")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle(f"{tm['ticker']} term structure — calendar violations {tm.get('calendarViolations', 0)}")
    fig.tight_layout()
    return _png(fig)
