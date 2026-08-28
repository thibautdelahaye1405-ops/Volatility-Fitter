"""Asynchronous cross-venue expiries for the backtest edge builders.

ROADMAP rider (wrap 2026-08-25a "Graph cross-venue async expiries"): the
``graph_edges`` taxonomy paired cross-asset nodes on the SAME expiry ISO
only, so an SPX Friday and a DAX Thursday never met. With
``EdgeConfig.cross_expiry_tol_days`` > 0 this module adds, for every
unordered ticker pair, the NEAREST-expiry relations of the production helper
``volfit.api.graph_params.nearest_cross_expiry_pairs`` (rungs with an exact
partner are excluded — they keep the standard same-ISO relation; matching
runs from both sides and dedups), classified by the very same ``_class_of``
decision the same-ISO loops use:

* **legacy directed edges** (``cross_expiry_directed_edges``): the class
  conductance attenuated by ``tol / (tol + gap_days)`` — continuous with the
  exact-match weight as the gap -> 0, exactly ``graph_params.lattice_weights``
  — with the class's vol-normalized beta (and the recurrence reverse edge)
  untouched: a gap within a few calendar days is second order on the
  sqrt-maturity scale, so only the trust is discounted;
* **message factors** (``cross_expiry_message_rows``): precision from the
  |dT|-decayed ``volfit.graph.message.cross_expiry_precision`` (normalized so
  the zero-gap limit is the class seed), and the §8.1 maturity-shape beta
  ``calendar_beta(t_receiver, t_informer, alpha_t)`` COMPOSED onto the
  sigma-ratio ATM beta while the shape handles carry the maturity beta alone
  (the same-ISO rows use unit shape betas — Phase-5 wing fix — because there
  is no maturity gap to transport). Orientation: ``sector_peer`` factors take
  the canonical SHORT receiver (§7.6, like calendar and the production
  cross-expiry factor); the directed hub classes (``broad_index`` /
  ``sector_etf``) keep the taxonomy orientation — the hub is the source —
  because ``graph_dynamic.SEMANTICS_BY_CLASS`` treats their source as the
  state driver and the relation class must not lie about who informs whom.

Everything here runs only when the tolerance is positive; the builders' own
loops are untouched, so the default edge lists remain a strict prefix.
"""

from __future__ import annotations

from collections import defaultdict

from volfit.api.graph_params import nearest_cross_expiry_pairs
from volfit.api.schemas import GraphEdgeInput, GraphMessageEdge
from volfit.graph.message import calendar_beta, cross_expiry_precision

from backtest.graph_edges import (
    MSG_CLASS_PRECISION,
    EdgeConfig,
    NodeKey,
    _class_of,
    cross_pair_edges,
    message_row,
)


def attenuation(gap_days: float, tol_days: float) -> float:
    """``tol / (tol + gap)`` — the lattice's trust discount for a nearest-
    expiry pair ``gap`` calendar days apart (1 as the gap -> 0)."""
    return tol_days / (tol_days + gap_days)


def async_pairs(
    nodes: list[NodeKey], tol_days: float
) -> list[tuple[NodeKey, NodeKey, int]]:
    """Every nearest-expiry cross-ticker node pair within ``tol_days``.

    Ticker pairs in sorted unordered order, ``((a, iso_a), (b, iso_b), gap)``
    with ``a < b``; within a pair the helper's own (sorted, deduped) order.
    Shared ISOs never appear (they carry the same-expiry relation). Empty for
    ``tol_days <= 0``."""
    ladders: dict[str, list[str]] = defaultdict(list)
    for ticker, iso in nodes:
        ladders[ticker].append(iso)
    tickers = sorted(ladders)
    out: list[tuple[NodeKey, NodeKey, int]] = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            for iso_a, iso_b, gap in nearest_cross_expiry_pairs(
                sorted(ladders[a]), sorted(ladders[b]), tol_days
            ):
                out.append(((a, iso_a), (b, iso_b), gap))
    return out


def cross_expiry_directed_edges(
    nodes: list[NodeKey], sigma: dict[NodeKey, float], cfg: EdgeConfig
) -> list[GraphEdgeInput]:
    """Legacy directed edges for the asynchronous pairs (see module doc).

    Both orderings of each pair are classified, like the same-ISO loop
    visiting every (influenced, informer) ordering: a hub pair yields the
    forward + recurrence-reverse edges once, a same-sector name pair yields
    one edge per direction. Weight = class conductance x ``attenuation``."""
    tol = cfg.cross_expiry_tol_days
    edges: list[GraphEdgeInput] = []
    for node_a, node_b, gap in async_pairs(nodes, tol):
        att = attenuation(gap, tol)
        for influenced, informer in ((node_a, node_b), (node_b, node_a)):
            hit = _class_of(informer, influenced, cfg)
            if hit is None:
                continue
            cls, beta_vn, w = hit
            edges.extend(cross_pair_edges(influenced, informer, w * att, beta_vn, cls, sigma, cfg))
    return edges


def _orient(
    node_a: NodeKey, node_b: NodeKey, t: dict[NodeKey, float], cfg: EdgeConfig
) -> tuple[NodeKey, NodeKey, str] | None:
    """``(receiver, informer, class)`` of one asynchronous pair, or None.

    A directed hub class (either ordering) wins and keeps its taxonomy
    orientation (hub = source); a peer relation takes the canonical SHORT
    receiver, ties broken lexicographically like the same-ISO loop."""
    for influenced, informer in ((node_a, node_b), (node_b, node_a)):
        hit = _class_of(informer, influenced, cfg)
        if hit is not None and hit[0] != "sector_peer":
            return influenced, informer, hit[0]
    if _class_of(node_b, node_a, cfg) is None:
        return None  # unrelated tickers (a peer class is symmetric in ordering)
    recv, inf = sorted((node_a, node_b), key=lambda n: (t.get(n, 0.0), n))
    return recv, inf, "sector_peer"


def cross_expiry_message_rows(
    nodes: list[NodeKey],
    sigma: dict[NodeKey, float],
    t: dict[NodeKey, float],
    cfg: EdgeConfig,
    alpha_t: float = 1.0,
    cross_precision_mult: float = 1.0,
) -> list[GraphMessageEdge]:
    """Message relation factors for the asynchronous pairs (see module doc).

    Precision: ``cross_expiry_precision(t_recv, t_inf, scale=seed * mult)``
    under the §9.2 defaults (``inverse_sqrt_gap``, epsilon 0.97 — the
    production request defaults; the builder does not see the campaign
    knobs). Betas: ATM = sigma ratio x maturity-shape beta (clipped like
    every row), skew/curv = the maturity-shape beta."""
    tol = cfg.cross_expiry_tol_days
    rows: list[GraphMessageEdge] = []
    for node_a, node_b, _gap in async_pairs(nodes, tol):
        rel = _orient(node_a, node_b, t, cfg)
        if rel is None:
            continue
        recv, inf, cls = rel
        t_r, t_i = max(t.get(recv, 0.0), 1e-9), max(t.get(inf, 0.0), 1e-9)
        sig_r, sig_i = sigma.get(recv, 0.0), sigma.get(inf, 0.0)
        ratio = sig_r / sig_i if sig_i > 0.0 else 1.0
        shape = calendar_beta(t_r, t_i, alpha_t)
        p = cross_expiry_precision(
            t_r, t_i, scale=MSG_CLASS_PRECISION[cls] * cross_precision_mult
        )
        rows.append(message_row(recv, inf, p, ratio * shape, cls, cfg, shape_beta=shape))
    return rows
