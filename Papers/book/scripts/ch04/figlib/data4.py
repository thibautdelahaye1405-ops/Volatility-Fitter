"""Frozen-snapshot access for the Chapter 4 figures.

Reads the same single data artifact as Chapters 2-3
(``data/lqd_paper_snapshot_20260804_0208.json``).  Chapter 4 uses two things
from it: the prepared mid quotes per node (the calibration targets of the
local-volatility fit, refitted here under the chapter's protocol) and the
stored per-expiry LQD fits (provenance: the smooth implied surface whose
Dupire ratio the 'field from the ledger' figure evaluates).  The snapshot is
never refetched and no live source is touched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import LQDSlice, build_slice

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
SNAPSHOT = DATA_DIR / "lqd_paper_snapshot_20260804_0208.json"


@dataclass(frozen=True)
class Node:
    """One (ticker, expiry) quote strip from the frozen snapshot."""

    ticker: str
    expiry: str
    t: float
    forward: float
    spot: float
    k: np.ndarray        # prepared quote log-moneyness
    iv_bid: np.ndarray
    iv_mid: np.ndarray
    iv_ask: np.ndarray
    lqd_params: LQDParams  # the snapshot's stored (haircut) fit -- provenance

    @property
    def w_mid(self) -> np.ndarray:
        """Total implied variance of the mid quotes (the fit target)."""
        return self.iv_mid**2 * self.t

    @property
    def n_quotes(self) -> int:
        return int(self.k.size)

    @property
    def days(self) -> int:
        return round(self.t * 365.0)

    @property
    def label(self) -> str:
        return f"{self.ticker} {self.expiry}"


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def manifest() -> dict:
    return _raw()["manifest"]


@lru_cache(maxsize=1)
def _nodes() -> dict[tuple[str, str], Node]:
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
                k=col["k"],
                iv_bid=col["ivBid"],
                iv_mid=col["ivMid"],
                iv_ask=col["ivAsk"],
                lqd_params=LQDParams(
                    float(lqd["L"]), float(lqd["R"]),
                    np.asarray(lqd["a"], dtype=float),
                ),
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


def stored_slice(n: Node) -> LQDSlice:
    """The snapshot's stored per-expiry LQD fit (provenance, never refitted)."""
    return build_slice(n.lqd_params)
