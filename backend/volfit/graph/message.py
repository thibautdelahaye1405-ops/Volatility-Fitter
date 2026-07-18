"""Precision-message graph operator — pairwise relation-factor assembly.

Implements the amended precision-message specification
(Docs/graph_precision_message_framework.md, 2026-07-18):

* §7.2  operator: ``Q_msg = Σ_edges p_ij (e_i − β_ij e_j)(e_i − β_ij e_j)ᵀ``
  — one Gaussian relation factor per edge, PSD for arbitrary real betas,
  sparse-ready by construction (each factor touches two nodes).
* §7.6  receiver conditional precision ``q_i``: a factor contributes ``p`` to
  its receiver and ``p·β²`` to its informer (the in-units mapping under the
  canonical one-factor-per-relation convention, ``p_rev = p_fwd / β²``).
* §8    calendar amplitude ``β = (T_informer / T_receiver)^alphaT`` with
  per-handle exponents (§8.5, all default 1.0).
* §9.2  calendar precision families; the inverse-sqrt-gap default carries the
  Phase-0 empirical seeds (p0 ≈ 1.7e3 vol⁻², epsT ≈ 0.97 √years — noise is
  nearly gap-flat at the day horizon; backtest/results/message_phase0.json).
* §9.4  per-handle precision units: ``messagePrecision`` is quoted in ATM-vol
  units; skew/curvature scale by ``(s_σ/s_h)²``.
* §14.2 node-linked innovation anchor (chosen 2026-07-18): ``κ_i =
  p_primary·(1−ρ_class)/ρ_class``, FIXED from the node's primary incident
  relation — corroborating edges then raise the effective transfer
  ``q/(κ+q)`` exactly as measured on the stored rows (0.391 → 0.561).
* §16.4 cycle beta-product diagnostics via a gauge-potential sweep.

Pure NumPy, dense materialization (universes are O(10²–10³) nodes; Phase 7
owns the sparse pass). No API or model imports — Phase 3 feeds edges in and
the posterior solve lives in ``message_posterior`` (Phase 2). Golden
contracts: tests/fixtures/graph_message_golden.json, locked before this
module existed (tests/test_graph_message_golden.py is the brute-force
reference; tests/test_graph_message.py drives THIS module).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np

N_HANDLES = 3  # (atm_vol, skew, curvature) — the v1 carrier (spec §3.2)

#: §9.4 — edge precision is defined in ATM-vol units; the skew/curvature
#: fields scale by (s_sigma / s_handle)^2 with the production per-handle
#: scales s = (0.03, 0.05, 0.5) (api.graph_service.GRAPH_PRIOR_HYPER).
HANDLE_PRECISION_SCALE: tuple[float, float, float] = (1.0, 0.36, 0.0036)

#: §9.2 Phase-0 empirical seeds (message_phase0.json): Var(e) = (epsT+√ΔT)/p0.
CALENDAR_PRECISION_SCALE = 1.7e3     # p0, 1/vol² (0.01 = 1 vol point)
CALENDAR_PRECISION_EPSILON = 0.97    # epsT, √years — dominates at day horizon

RELATION_CLASSES = ("calendar", "broad_index", "sector_etf", "sector_peer", "custom")


@dataclass(frozen=True)
class MessageEdge:
    """One directed relation factor: ``z_receiver ≈ β · z_informer`` with
    conditional relation precision ``p`` quoted in the RECEIVER's units
    (§7.1/§7.6). ``beta`` is per-handle (atm, skew, curvature)."""

    receiver: str
    informer: str
    precision: float
    beta: tuple[float, float, float]
    relation_class: str = "custom"


def message_edge(
    receiver: str,
    informer: str,
    precision: float,
    beta: float | Sequence[float] = 1.0,
    relation_class: str = "custom",
) -> MessageEdge:
    """Convenience constructor: a scalar beta broadcasts to all three handles."""
    if receiver == informer:
        raise ValueError(f"self-relation on node {receiver!r}")
    if not (precision > 0.0) or not math.isfinite(precision):
        raise ValueError(f"edge precision must be finite and > 0, got {precision}")
    b3 = (
        (float(beta),) * N_HANDLES
        if isinstance(beta, (int, float))
        else tuple(float(x) for x in beta)
    )
    if len(b3) != N_HANDLES:
        raise ValueError(f"beta must be scalar or length-{N_HANDLES}, got {beta!r}")
    return MessageEdge(receiver, informer, precision, b3, relation_class)


# ------------------------------------------------------------------- calendar
def calendar_beta(t_receiver: float, t_informer: float, alpha: float = 1.0) -> float:
    """§8.1 maturity-shape amplitude ``(T_informer / T_receiver)^alphaT``.

    ``alphaT = 1`` (the locked shape default) is constant total-variance
    injection; the amplitude LEVEL rho is a separate, adjudicated multiplier
    applied through the §14.2 anchor, never through this beta."""
    if t_receiver <= 0.0 or t_informer <= 0.0:
        raise ValueError("maturities must be positive year fractions")
    return (t_informer / t_receiver) ** alpha


def calendar_message_precision(
    t_a: float,
    t_b: float,
    *,
    scale: float = CALENDAR_PRECISION_SCALE,
    epsilon: float = CALENDAR_PRECISION_EPSILON,
    rule: str = "inverse_sqrt_gap",
    log_scale: float = 1.0,
) -> float:
    """§9.2 calendar relation precision, quoted in canonical-receiver units.

    Families: ``inverse_sqrt_gap`` (product default, ``p0/(eps+√|ΔT|)``),
    ``constant``, and ``log_distance`` (``p0·exp(−|log(Ta/Tb)|/ℓ)``)."""
    if rule == "inverse_sqrt_gap":
        return scale / (epsilon + math.sqrt(abs(t_a - t_b)))
    if rule == "constant":
        return scale
    if rule == "log_distance":
        return scale * math.exp(-abs(math.log(t_a / t_b)) / log_scale)
    raise ValueError(f"unknown calendar precision rule {rule!r}")


def expand_calendar_ladder(
    maturities: Mapping[str, float],
    *,
    alpha: float | Sequence[float] = 1.0,
    scale: float = CALENDAR_PRECISION_SCALE,
    epsilon: float = CALENDAR_PRECISION_EPSILON,
    rule: str = "inverse_sqrt_gap",
) -> list[MessageEdge]:
    """One factor per ADJACENT expiry pair, canonical receiver = the SHORTER
    maturity (§7.6) — so a bidirectional auto-lattice cannot double-count a
    relation. The implied reverse amplitude is ``1/β`` (reciprocal, §8.3) and
    the implied reverse precision is ``p·β²`` (the §7.6 identity)."""
    a3 = (
        (float(alpha),) * N_HANDLES
        if isinstance(alpha, (int, float))
        else tuple(float(x) for x in alpha)
    )
    ladder = sorted(maturities.items(), key=lambda kv: kv[1])
    edges: list[MessageEdge] = []
    for (short, t_s), (long_, t_l) in zip(ladder[:-1], ladder[1:]):
        beta = tuple(calendar_beta(t_s, t_l, a) for a in a3)
        p = calendar_message_precision(t_s, t_l, scale=scale, epsilon=epsilon, rule=rule)
        edges.append(MessageEdge(short, long_, p, beta, "calendar"))
    return edges


# ------------------------------------------------------------------- assembly
@dataclass(frozen=True)
class MessageOperator:
    """The assembled §7.2 operator for ONE handle: dense PSD ``q_matrix``
    (Q_msg), the §7.6 receiver conditional precisions ``receiver_precision``
    (q_i), and the raw factor triplets ``factors`` = (i, j, p, β) rows kept
    for the Phase-2 information-form assembly and diagnostics."""

    nodes: tuple[str, ...]
    handle: int
    q_matrix: np.ndarray
    receiver_precision: np.ndarray
    factors: tuple[tuple[int, int, float, float], ...]

    @property
    def index(self) -> dict[str, int]:
        return {n: i for i, n in enumerate(self.nodes)}


def _validated_factors(
    nodes: Sequence[str],
    edges: Iterable[MessageEdge],
    handle: int,
    handle_scale: Sequence[float],
) -> list[tuple[int, int, float, float]]:
    index = {n: i for i, n in enumerate(nodes)}
    if len(index) != len(nodes):
        raise ValueError("duplicate node names")
    out = []
    for e in edges:
        if e.receiver == e.informer:
            raise ValueError(f"self-relation on node {e.receiver!r}")
        if not (e.precision > 0.0) or not math.isfinite(e.precision):
            raise ValueError(f"edge precision must be finite and > 0, got {e.precision}")
        try:
            i, j = index[e.receiver], index[e.informer]
        except KeyError as exc:
            raise ValueError(f"edge references unknown node {exc.args[0]!r}") from exc
        out.append((i, j, e.precision * handle_scale[handle], float(e.beta[handle])))
    return out


def build_message_operator(
    nodes: Sequence[str],
    edges: Iterable[MessageEdge],
    handle: int = 0,
    *,
    handle_scale: Sequence[float] = HANDLE_PRECISION_SCALE,
) -> MessageOperator:
    """Assemble ``Q_msg`` for one handle from the factor list (§7.2).

    Each factor is the rank-one PSD block ``p·(e_i − β e_j)(e_i − β e_j)ᵀ``;
    the sum is symmetric PSD for arbitrary real betas. ``receiver_precision``
    applies the §7.6 in-units mapping (p to the receiver, p·β² to the
    informer), so it is exactly the golden-fixture ``q``."""
    n = len(nodes)
    factors = _validated_factors(nodes, edges, handle, handle_scale)
    q = np.zeros((n, n))
    qvec = np.zeros(n)
    for i, j, p, b in factors:
        q[i, i] += p
        q[j, j] += p * b * b
        q[i, j] -= p * b
        q[j, i] -= p * b
        qvec[i] += p
        qvec[j] += p * b * b
    return MessageOperator(tuple(nodes), handle, q, qvec, tuple(factors))


# -------------------------------------------------------------------- anchors
def anchor_precisions(
    nodes: Sequence[str],
    edges: Iterable[MessageEdge],
    rho_by_class: Mapping[str, float],
    handle: int = 0,
    *,
    handle_scale: Sequence[float] = HANDLE_PRECISION_SCALE,
) -> np.ndarray:
    """§14.2 node-linked innovation anchor (chosen 2026-07-18).

    For each node, the PRIMARY incident relation is the factor with the
    largest precision in the node's units (p on the receiver side, p·β² on
    the informer side); then ``κ = p_primary·(1−ρ)/ρ`` with ρ the primary
    relation's class multiplier. FIXED at build — never rescaled as further
    edges arrive, which is what makes corroboration lift the effective
    transfer ``q/(κ+q)`` (validated to 0.3% on the stored benchmark rows).
    ``ρ = 1`` (the desk preset) and isolated nodes give ``κ = 0`` exactly."""
    index = {n: i for i, n in enumerate(nodes)}
    best_p = np.zeros(len(nodes))
    best_rho = np.ones(len(nodes))
    for e in edges:
        p_h = e.precision * handle_scale[handle]
        rho = float(rho_by_class.get(e.relation_class, 1.0))
        if not (0.0 < rho <= 1.0):
            raise ValueError(f"amplitude multiplier must be in (0, 1], got {rho}")
        b = e.beta[handle]
        for node, p_units in ((e.receiver, p_h), (e.informer, p_h * b * b)):
            i = index[node]
            if p_units > best_p[i]:
                best_p[i] = p_units
                best_rho[i] = rho
    return best_p * (1.0 - best_rho) / best_rho


# ----------------------------------------------------------- cycle diagnostics
@dataclass(frozen=True)
class CycleDiagnostic:
    """One inconsistent cycle, reported at the non-tree edge that closes it:
    ``product`` is the implied beta product around that cycle (NaN marks a
    nonpositive beta, which the gauge sweep cannot place)."""

    receiver: str
    informer: str
    product: float


def cycle_beta_products(
    nodes: Sequence[str],
    edges: Iterable[MessageEdge],
    handle: int = 0,
    *,
    tol: float = 1e-9,
) -> list[CycleDiagnostic]:
    """§16.4 cycle-consistency sweep in gauge-potential form.

    A beta structure is cycle-consistent iff ``β_ij = g_i/g_j`` for node
    potentials g (every cycle product is then exactly 1). Sweep a spanning
    forest assigning ``φ = log g`` via union-find-with-offsets; every edge
    that closes a cycle implies the product ``exp(logβ − (φ_i − φ_j))`` around
    it — flagged when it differs from 1 beyond ``tol``. Linear time, and any
    inconsistent cycle is caught at some closing edge."""
    index = {n: i for i, n in enumerate(nodes)}
    parent = list(range(len(nodes)))
    offset = [0.0] * len(nodes)  # φ(x) − φ(parent[x])

    def find(x: int) -> tuple[int, float]:
        path = []
        while parent[x] != x:
            path.append(x)
            x = parent[x]
        acc = 0.0
        for y in reversed(path):  # compress with accumulated offsets
            acc += offset[y]
            parent[y], offset[y] = x, acc
        return x, 0.0

    out: list[CycleDiagnostic] = []
    for e in edges:
        b = e.beta[handle]
        if not (b > 0.0) or not math.isfinite(b):
            out.append(CycleDiagnostic(e.receiver, e.informer, float("nan")))
            continue
        i, j = index[e.receiver], index[e.informer]
        ri, _ = find(i)
        rj, _ = find(j)
        phi_i = offset[i] if parent[i] != i else 0.0
        phi_j = offset[j] if parent[j] != j else 0.0
        log_b = math.log(b)
        if ri != rj:  # tree edge: fix φ_i − φ_j = log β by re-rooting rj
            parent[rj] = ri
            offset[rj] = phi_i - log_b - phi_j
        else:
            product = math.exp(log_b - (phi_i - phi_j))
            if abs(product - 1.0) > tol:
                out.append(CycleDiagnostic(e.receiver, e.informer, product))
    return out
