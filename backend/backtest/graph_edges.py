"""Directed edge construction for the graph LOO backtest (roadmap Phase 6).

Builds the user-specified directed graph topology over a captured universe:

  * **calendar** (same ticker, adjacent expiries, both directions): high
    conductance, ``beta = sqrt(T_informer / T_influenced)`` — a vol move at one
    expiry maps to its neighbour scaled by the sqrt-maturity ratio (short-dated
    vol-of-vol is larger, so a long expiry moves less than the short that drove it,
    and vice-versa);
  * **index -> single name** (same expiry): vol-normalized ``beta = 0.7``,
    moderate conductance — the systematic market factor;
  * **sector-ETF -> single name** (same sector, same expiry): ``beta = 0.8``,
    higher conductance;
  * **single name -> single name** (same sector, same expiry, both directions):
    ``beta = 0.6``, moderate conductance;
  * every other edge: absent (``beta = 0``).

DIRECTION CONVENTION (critical — see volfit.graph.build): the raw weight ``w_ij``
means "j is relevant when predicting i", and a ``GraphEdgeInput`` writes
``w[from, to]``. So **information flows from ``toTicker`` to ``fromTicker``** — the
``to`` node INFORMS the ``from`` node. To encode "the index informs the name" we
therefore emit ``fromTicker=NAME, toTicker=INDEX`` (the influenced node is ``from``,
the informer is ``to``). The per-edge beta ``beta_ij`` (i=from, j=to) then scales
"the from-node's move per unit to-node move", exactly the vol-beta of name on index.

**Vol-normalized beta:** the handles propagate in absolute vol units, so a
vol-normalized ``beta_vn`` (a relative-move multiplier) becomes the absolute edge
beta ``beta_vn * sigma_from / sigma_to`` (v1: the same factor on all three handles;
flagged for per-handle refinement). ``sigma`` is each node's baseline (transported-
prior) ATM vol — the pre-move scale.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from volfit.api.schemas import GraphEdgeInput

from backtest.universe import FULL

NodeKey = tuple[str, str]  # (ticker, expiry-ISO)

#: Asset taxonomy from the backtest universe (FULL is the superset of PILOT).
_SPECS = {a.ticker: a for a in FULL}
#: ETFs are american-settled non-index roots; the only two in the universe are the
#: broad international funds (no US sector ETF is captured yet, so the ETF->name
#: edge class is dormant on the current pilot fixtures).
_ETF_TICKERS = frozenset({"EEM", "EFA"})


def asset_kind(ticker: str) -> str:
    """``"index"`` (sector=index) | ``"etf"`` | ``"name"`` (single name)."""
    spec = _SPECS.get(ticker)
    if spec is not None and spec.sector == "index":
        return "index"
    if ticker in _ETF_TICKERS:
        return "etf"
    return "name"


def asset_sector(ticker: str) -> str:
    spec = _SPECS.get(ticker)
    return spec.sector if spec is not None else "unknown"


@dataclass(frozen=True)
class BetaOverrides:
    """Learned vol-normalized beta overrides (the backtest.learn_betas artifact,
    R3 item 14). Every field defaults to "no override": a None/missing entry
    falls back to the EdgeConfig prior, so an artifact whose cells were all
    auto-rejected reproduces the default edge list bit-for-bit."""

    index_by_name: dict = field(default_factory=dict)  # name -> learned beta_vn
    name_beta: float | None = None  # same-sector name<->name class value
    etf_beta: float | None = None  # sector-ETF -> name class value
    calendar_mult: float | None = None  # multiplier on the sqrt(T ratio) betas


@dataclass(frozen=True)
class EdgeConfig:
    """Directed-edge weights (conductance / "precision") + vol-normalized betas."""

    cal_weight: float = 10.0       # calendar conductance (high precision)
    index_weight: float = 2.0      # index -> name (moderate)
    etf_weight: float = 4.0        # sector-ETF -> name (higher)
    name_weight: float = 2.0       # name -> name same sector (moderate)
    beta_index: float = 0.7
    beta_etf: float = 0.8
    beta_name: float = 0.6
    #: Which index tickers act as cross-asset market hubs (default the broad index;
    #: connecting every index to every name would multiply-count the market factor).
    market_indices: tuple[str, ...] = ("SPX",)
    beta_cap: float = 3.0          # clip vol-ratio / sqrt-T betas to a sane band
    handles: tuple[str, ...] = field(default=("atm", "skew", "curv"))
    #: Weight fraction of the REVERSE cross edge (name informs its index/ETF
    #: informer). 2026-07-09 root-cause: with informer->name edges only, single
    #: names are TRANSIENT states of the directed walk — their stationary mass
    #: pi is exactly 0, so the reversibilized conductance c_ij = f(pi, K) on
    #: every edge touching a name VANISHES and the increment prior decouples
    #: dark names entirely (liquid_split skill was 0.000 in the pilot AND the
    #: 25-asset benchmark for this reason, NOT because of baseline-precision
    #: pinning). The reverse edge restores stationary mass; its beta is the
    #: INVERSE of the forward beta, so both directions encode the same linear
    #: relation and no second economic claim is introduced. 0 disables
    #: (reproduces the legacy, disconnected behaviour).
    cross_reverse_frac: float = 1.0
    #: Learned beta overrides (backtest.learn_betas). None = the analytic
    #: defaults above, byte-identical.
    overrides: BetaOverrides | None = None


def _clip(beta: float, cfg: EdgeConfig) -> float:
    return float(min(max(beta, 0.0), cfg.beta_cap))


def _edge(frm: NodeKey, to: NodeKey, weight: float, beta: float) -> GraphEdgeInput:
    """A directed edge: ``to`` INFORMS ``frm`` (info flows to->from). Same beta on
    all three handles in v1."""
    return GraphEdgeInput(
        fromTicker=frm[0], fromExpiry=frm[1], toTicker=to[0], toExpiry=to[1],
        weight=weight, betaAtmVol=beta, betaSkew=beta, betaCurv=beta,
    )


#: Phase-0 empirical cross-class message precision seeds (1/vol^2, ATM-vol
#: units; backtest/results/message_phase0.json): residual message noise of
#: 0.87 / 1.05 vol points for index->name / sector-peer relations. The ETF
#: class was unmeasurable (dormant on this universe) and sits between them.
MSG_INDEX_PRECISION = 1.3e4
MSG_PEER_PRECISION = 0.9e4
MSG_ETF_PRECISION = 1.1e4


def build_message_edges(
    nodes: list[NodeKey],
    sigma: dict[NodeKey, float],
    t: dict[NodeKey, float],
    cfg: EdgeConfig | None = None,
    alpha_t: float = 1.0,
    cross_precision_mult: float = 1.0,
) -> list["GraphMessageEdge"]:
    """The SAME economic taxonomy as ``build_directed_edges``, expressed as
    precision-message relation factors (message arc P4) — so the adjudication
    compares OPERATORS on a like-for-like topology, not topologies.

    One factor per relation (the pairwise operator needs no reverse rows and
    no ``cross_reverse_frac`` fix — a Gaussian MRF has no transient states):

    * calendar: adjacent selected expiries per ticker, canonical receiver =
      the SHORTER maturity (spec 7.6), shape beta ``(T_long/T_short)^alpha_t``
      (raw vol units, same ticker), precision from the spec-9.2 distance rule
      (``precisionRule="calendar_distance"`` — derived at solve time);
    * broad_index: market hub informs each single name, ``beta`` =
      ``sigma_name/sigma_index`` (the unit vol-normalized relation — the
      amplitude LEVEL rides the request's amplitude multipliers via the
      spec-14.2 anchor, never the beta);
    * sector_etf: same-sector ETF informs the name, same beta convention;
    * sector_peer: one factor per unordered same-sector name pair,
      lexicographic receiver, ``beta = sigma_receiver/sigma_informer``.

    Betas are clipped to ``cfg.beta_cap`` like the legacy builder."""
    from volfit.api.schemas import GraphMessageEdge

    cfg = cfg or EdgeConfig()
    rows: list[GraphMessageEdge] = []

    def _row(recv: NodeKey, inf: NodeKey, p: float, beta: float, cls: str,
             rule: str = "explicit") -> GraphMessageEdge:
        b = _clip(beta, cfg)
        return GraphMessageEdge(
            sourceTicker=inf[0], sourceExpiry=inf[1],
            targetTicker=recv[0], targetExpiry=recv[1],
            messagePrecision=p, betaAtmVol=b, betaSkew=b, betaCurv=b,
            relationClass=cls, precisionRule=rule,
        )

    by_ticker: dict[str, list[NodeKey]] = defaultdict(list)
    for n in nodes:
        by_ticker[n[0]].append(n)
    for ns in by_ticker.values():
        ns.sort(key=lambda n: t.get(n, 0.0))
        for short, long_ in zip(ns[:-1], ns[1:]):  # t[short] <= t[long_]
            ts, tl = max(t.get(short, 0.0), 1e-9), max(t.get(long_, 0.0), 1e-9)
            rows.append(_row(short, long_, 1.0, (tl / ts) ** alpha_t,
                             "calendar", rule="calendar_distance"))

    by_iso: dict[str, list[NodeKey]] = defaultdict(list)
    for n in nodes:
        by_iso[n[1]].append(n)
    for ns in by_iso.values():
        names = sorted(n for n in ns if asset_kind(n[0]) == "name")
        for influenced in names:
            sec = asset_sector(influenced[0])
            sig_i = sigma.get(influenced, 0.0)
            for informer in ns:
                if informer == influenced:
                    continue
                kind = asset_kind(informer[0])
                sig_j = sigma.get(informer, 0.0)
                ratio = sig_i / sig_j if sig_j > 0.0 else 1.0
                if kind == "index" and informer[0] in cfg.market_indices:
                    rows.append(_row(
                        influenced, informer,
                        MSG_INDEX_PRECISION * cross_precision_mult, ratio,
                        "broad_index",
                    ))
                elif kind == "etf" and asset_sector(informer[0]) == sec:
                    rows.append(_row(
                        influenced, informer,
                        MSG_ETF_PRECISION * cross_precision_mult, ratio,
                        "sector_etf",
                    ))
                elif (
                    kind == "name"
                    and asset_sector(informer[0]) == sec
                    and informer > influenced  # one factor per unordered pair
                ):
                    rows.append(_row(
                        influenced, informer,
                        MSG_PEER_PRECISION * cross_precision_mult, ratio,
                        "sector_peer",
                    ))
    return rows


def build_directed_edges(
    nodes: list[NodeKey],
    sigma: dict[NodeKey, float],
    t: dict[NodeKey, float],
    cfg: EdgeConfig | None = None,
) -> list[GraphEdgeInput]:
    """The directed edge list (calendar + cross-asset) for one captured universe.

    ``sigma`` / ``t`` are each node's baseline ATM vol and calendar year-fraction.
    Cross-asset edges connect same-expiry nodes; only single names are *influenced*
    cross-asset (indices / ETFs receive calendar edges only)."""
    cfg = cfg or EdgeConfig()
    ov = cfg.overrides
    cal_mult = 1.0 if ov is None or ov.calendar_mult is None else ov.calendar_mult
    edges: list[GraphEdgeInput] = []

    # --- calendar: each adjacent expiry pair informs the other (both directions) ---
    by_ticker: dict[str, list[NodeKey]] = defaultdict(list)
    for n in nodes:
        by_ticker[n[0]].append(n)
    for ns in by_ticker.values():
        ns.sort(key=lambda n: t.get(n, 0.0))
        for a, b in zip(ns[:-1], ns[1:]):  # t[a] <= t[b]
            ta, tb = max(t.get(a, 0.0), 1e-9), max(t.get(b, 0.0), 1e-9)
            # b (long) informs a (short): beta = sqrt(T_to / T_from) = sqrt(tb/ta) >= 1
            edges.append(_edge(a, b, cfg.cal_weight, _clip(cal_mult * math.sqrt(tb / ta), cfg)))
            # a (short) informs b (long): beta = sqrt(ta/tb) <= 1
            edges.append(_edge(b, a, cfg.cal_weight, _clip(cal_mult * math.sqrt(ta / tb), cfg)))

    # --- cross-asset, same expiry: informer (to) -> influenced single name (from) ---
    by_iso: dict[str, list[NodeKey]] = defaultdict(list)
    for n in nodes:
        by_iso[n[1]].append(n)
    for ns in by_iso.values():
        for influenced in ns:
            if asset_kind(influenced[0]) != "name":
                continue  # only single names are influenced cross-asset
            sec = asset_sector(influenced[0])
            for informer in ns:
                if informer == influenced:
                    continue
                kind = asset_kind(informer[0])
                if kind == "index" and informer[0] in cfg.market_indices:
                    beta_vn, w = cfg.beta_index, cfg.index_weight
                    if ov is not None:  # learned per-name index beta
                        beta_vn = ov.index_by_name.get(influenced[0], beta_vn)
                elif kind == "etf" and asset_sector(informer[0]) == sec:
                    beta_vn, w = cfg.beta_etf, cfg.etf_weight
                    if ov is not None and ov.etf_beta is not None:
                        beta_vn = ov.etf_beta
                elif kind == "name" and asset_sector(informer[0]) == sec:
                    beta_vn, w = cfg.beta_name, cfg.name_weight
                    if ov is not None and ov.name_beta is not None:
                        beta_vn = ov.name_beta
                else:
                    continue  # every other edge: beta 0 (omitted)
                sig_from = sigma.get(influenced, 0.0)
                sig_to = sigma.get(informer, 0.0)
                ratio = sig_from / sig_to if sig_to > 0.0 else 1.0
                beta_fwd = _clip(beta_vn * ratio, cfg)
                edges.append(_edge(influenced, informer, w, beta_fwd))
                # Reverse edge for index/ETF informers only (name<->name pairs are
                # already emitted in both directions by this loop): keeps single
                # names recurrent so their conductance is nonzero (see EdgeConfig).
                if kind != "name" and cfg.cross_reverse_frac > 0.0:
                    edges.append(_edge(
                        informer, influenced, w * cfg.cross_reverse_frac,
                        _clip(1.0 / max(beta_fwd, 1e-6), cfg),
                    ))
    return edges
