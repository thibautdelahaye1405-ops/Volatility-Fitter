"""Frozen-snapshot access for the LQD paper figures.

The single data artifact is ``data/lqd_paper_snapshot_20260804_0208.json``.
Real-market slices are REBUILT from the stored (L, R, a) parameters via the
production ``build_slice`` -- never refitted -- and the rebuild reproduces
the frozen display curves to 0.0 vol bp (checked in ``verify_rebuild``).

Prepared-quote columns (introspected): k, strike, ivBid, ivMid, ivAsk,
wMid, eep.  The haircut band (h = manifest fitSettings.haircut = 0.005)
follows the production rule: lo = min(ivBid + h, ivMid),
hi = max(ivMid, ivAsk - h) -- a quote tighter than 2h degenerates to mid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from volfit.models.lqd.basis import LQDParams, endpoint_scales, lee_slopes
from volfit.models.lqd.quadrature import LQDSlice, build_slice

from macros import STORE, num

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SNAPSHOT = DATA_DIR / "lqd_paper_snapshot_20260804_0208.json"

# Featured nodes (see review/FIGURES_NOTES.md for the selection rationale).
SPY_DEC = ("SPY", "2026-12-18")      # the deep-dive / worked-ticket node
NVDA_SHORT = ("NVDA", "2026-08-05")  # the 1-day node, order guard live
NVDA_LONG = ("NVDA", "2027-12-17")   # the longest NVDA maturity (1.37 y)
SPY_PAIR = (("SPY", "2026-08-05"), ("SPY", "2026-08-07"))  # calendar forensics


@dataclass
class Node:
    """One fitted (ticker, expiry) smile from the frozen snapshot."""

    ticker: str
    expiry: str
    t: float
    forward: float
    spot: float
    discount: float
    var_swap_vol: float
    rms_bp: float
    max_iv_bp: float
    params: LQDParams
    k: np.ndarray        # prepared quote log-moneyness
    strike: np.ndarray
    iv_bid: np.ndarray
    iv_mid: np.ndarray
    iv_ask: np.ndarray
    curve_k: np.ndarray  # frozen display curve (241 points, [-1.4, 1.4])
    curve_iv: np.ndarray
    curve_w: np.ndarray
    haircut: float
    _slice: LQDSlice | None = field(default=None, repr=False)

    # ------------------------------------------------------------- rebuild
    @property
    def slice(self) -> LQDSlice:
        """Production slice rebuilt from the frozen (L, R, a) -- no refit."""
        if self._slice is None:
            self._slice = build_slice(self.params)
        return self._slice

    # ---------------------------------------------------------------- band
    @property
    def band_lo(self) -> np.ndarray:
        return np.minimum(self.iv_bid + self.haircut, self.iv_mid)

    @property
    def band_hi(self) -> np.ndarray:
        return np.maximum(self.iv_mid, self.iv_ask - self.haircut)

    # ----------------------------------------------------------- residuals
    def model_iv(self, k: np.ndarray | float) -> np.ndarray:
        return self.slice.implied_vol(k, self.t)

    @property
    def residual_bp(self) -> np.ndarray:
        """Model minus mid at the calibration quotes, in vol bp."""
        return 1e4 * (np.asarray(self.model_iv(self.k)) - self.iv_mid)

    # -------------------------------------------------------- descriptors
    @property
    def order(self) -> int:
        """Effective Legendre order N (quote-count guard already applied)."""
        return self.params.order

    @property
    def n_quotes(self) -> int:
        return int(self.k.size)

    @property
    def days(self) -> int:
        return round(self.t * 365.0)

    def tails(self) -> tuple[float, float, float, float]:
        """(A_L, A_R, beta_L, beta_R)."""
        a_l, a_r = endpoint_scales(self.params)
        b_l, b_r = lee_slopes(self.params)
        return a_l, a_r, b_l, b_r


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def manifest() -> dict:
    return _raw()["manifest"]


@lru_cache(maxsize=1)
def _nodes() -> dict[tuple[str, str], Node]:
    haircut = float(manifest()["fitSettings"]["haircut"])
    out: dict[tuple[str, str], Node] = {}
    for ticker in _raw()["tickers"]:
        for raw in ticker["nodes"]:
            cols = raw["inputs"]["preparedColumns"]
            prepared = np.asarray(raw["inputs"]["prepared"], dtype=float)
            col = {name: prepared[:, i] for i, name in enumerate(cols)}
            lqd = raw["lqdParams"]
            node = Node(
                ticker=ticker["ticker"],
                expiry=raw["expiry"],
                t=float(raw["t"]),
                forward=float(raw["forward"]),
                spot=float(ticker["spot"]),
                discount=float(raw["discount"]),
                var_swap_vol=float(raw["varSwapVol"]),
                rms_bp=float(raw["quality"]["rmsBp"]),
                max_iv_bp=float(raw["quality"]["maxIvBp"]),
                params=LQDParams(
                    float(lqd["L"]), float(lqd["R"]),
                    np.asarray(lqd["a"], dtype=float),
                ),
                k=col["k"], strike=col["strike"], iv_bid=col["ivBid"],
                iv_mid=col["ivMid"], iv_ask=col["ivAsk"],
                curve_k=np.asarray([c["k"] for c in raw["curve"]]),
                curve_iv=np.asarray([c["iv"] for c in raw["curve"]]),
                curve_w=np.asarray([c["w"] for c in raw["curve"]]),
                haircut=haircut,
            )
            out[(node.ticker, node.expiry)] = node
    return out


def node(ticker: str, expiry: str) -> Node:
    return _nodes()[(ticker, expiry)]


def nodes(ticker: str | None = None) -> list[Node]:
    """All nodes (optionally one ticker), sorted by maturity."""
    values = [
        n for n in _nodes().values() if ticker is None or n.ticker == ticker
    ]
    return sorted(values, key=lambda n: (n.ticker, n.t))


def verify_rebuild(tol_bp: float = 0.05) -> float:
    """Worst |rebuilt - frozen| display-curve IV gap across all 16 nodes."""
    worst = 0.0
    for n in nodes():
        gap = 1e4 * np.max(np.abs(n.model_iv(n.curve_k) - n.curve_iv))
        worst = max(worst, float(gap))
    if worst > tol_bp:
        raise RuntimeError(
            f"snapshot rebuild mismatch: {worst:.3f} bp > {tol_bp} bp"
        )
    return worst


def add_snapshot_macros() -> None:
    """Snapshot-level numbers the introduction and the data annex quote."""
    man = manifest()
    all_rms = np.array([n.rms_bp for n in nodes()])
    worst = max(nodes(), key=lambda n: n.rms_bp)
    spy, nvda = node(*SPY_DEC), node(*NVDA_SHORT)
    STORE.add("snapshot", "RefDate", man["referenceDate"],
              "snapshot reference date (US session of record)")
    STORE.add("snapshot", "SpySpot", num(spy.spot, 2), "SPY spot")
    STORE.add("snapshot", "NvdaSpot", num(nvda.spot, 2), "NVDA spot")
    STORE.add("snapshot", "NodeCount", str(len(nodes())),
              "fitted nodes in the snapshot")
    STORE.add("snapshot", "MedianRmsBp", num(np.median(all_rms), 1),
              "median per-node rms fit error, vol bp")
    STORE.add("snapshot", "WorstRmsBp", num(all_rms.max(), 1),
              "worst per-node rms fit error, vol bp")
    STORE.add("snapshot", "WorstRmsNode",
              f"{worst.ticker} {worst.expiry}", "node carrying the worst rms")
    STORE.add("snapshot", "HaircutVolPt",
              num(100 * float(man["fitSettings"]["haircut"]), 1),
              "haircut band shrink, vol points")
    STORE.add("snapshot", "SnapshotOrder",
              str(int(man["fitSettings"]["nOrder"])),
              "configured Legendre order N (per-slice quote guard applies)")
    STORE.add("snapshot", "RebuildWorstBp", num(verify_rebuild(), 3),
              "worst |rebuilt - frozen| display-curve IV gap, vol bp")
