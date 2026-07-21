"""Dirichlet harmonic solver for the dynamic-harmonic framework (Phase 3).

Implements Docs/dynamic_directed_harmonic_graph_framework.md §7 (reciprocal
beta-harmonic completion) as an explicit boundary-value solver, one handle at
a time:

* §7.3  EXACT hard-boundary partition — boundary rows/columns are eliminated,
  never emulated with large precision (§13.2).
* §7.4  uncertain-but-clamped boundary: edge-residual covariance
  ``Omega = P^-1 + B_S V_S B_S^T`` — the boundary's central values stay
  clamped while its calibration uncertainty widens dependent free nodes and
  CORRELATES everything fed by the same boundary node.
* §7.5  directed predictions and stale/ghost observations enter as UNARY
  factors, never as pairwise edges to their parents — the harmonic solve can
  combine them with calendar support but cannot update their sources.
  Both D6 forms are supported: independent per-node anchors (diagonal R_D)
  and a JOINT anchored block whose covariance comes from
  ``DirectedPass.covariance`` (low-rank/full R_D) — the Phase-5 benchmark
  adjudicates which ships as default.
* §7.6  screened option: ``kappa > 0`` connects free nodes to a
  zero-innovation ground (a screened/killed Laplacian — retention, not
  amplitude; reported distinctly from the pure harmonic mode).
* §7.7  supported-component detection: a component with no boundary and no
  unary anchor stays at ZERO innovation with ``no_active_observation_path``
  and explicitly broad variance — no precision is invented (a screen alone
  is a ground, not information).
* §7.2  strict harmonic mode validates positive, cycle-consistent betas via
  the §16.4 gauge sweep (``cycle_beta_products``).

Reciprocal relations are ``MessageEdge`` rows (canonical orientation =
receiver; the §7.1 factor is identical to the precision-message factor).
Precisions are taken as supplied — per-handle unit scaling is the Phase-4
orchestration's job. Dense per-component algebra by design (§13.3: the dense
reference is the golden contract; Phase 7 owns Woodbury/sparsity).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np

from volfit.graph.message import MessageEdge, cycle_beta_products

#: §7.7 — the honest no-support variance (mirrors message_posterior).
NO_SUPPORT_VARIANCE = np.inf


class HarmonicGaugeError(ValueError):
    """Strict harmonic mode requires positive, cycle-consistent betas."""


@dataclass(frozen=True, eq=False)
class HarmonicPosterior:
    """One handle's boundary-value solution over all nodes.

    ``sources`` lists every information source as ``(kind, node)`` with
    ``kind in {"boundary", "unary"}``; ``gain @ source_values == mean``
    exactly (boundary rows are unit on themselves), which is the §6.6-style
    attribution contract the reconstruction adapter consumes."""

    nodes: tuple[str, ...]
    handle: int
    mean: np.ndarray                 # (N,)
    variance: np.ndarray             # (N,) — boundary rows carry V_S
    posterior_covariance: np.ndarray  # (N, N) — free blocks per component
    boundary: np.ndarray             # boundary node indices
    no_active_observation_path: np.ndarray  # bool (N,)
    component: np.ndarray            # int labels (N,)
    sources: tuple[tuple[str, str], ...]
    source_values: np.ndarray        # (n_sources,)
    gain: np.ndarray                 # (N, n_sources)

    def attribution(self, i: int):
        """(sources, source_values, contributions) — contributions sum to
        ``mean[i]`` for every supported node."""
        row = self.gain[i]
        return self.sources, self.source_values, row * self.source_values


def _components(n, edges, index, extra_precision, joint_idx):
    """Union-find over beta!=0 factor coupling, any extra off-diagonals
    (§17 Phase-3 item 7: hybrid support detection), and the joint unary
    block — a correlated anchor couples its nodes in the posterior, so they
    must be solved as one component."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for e, beta in edges:
        if beta != 0.0:
            union(index[e.receiver], index[e.informer])
    if extra_precision is not None:
        rows, cols = np.nonzero(extra_precision)
        for i, j in zip(rows, cols):
            if i != j:
                union(int(i), int(j))
    for a, b in zip(joint_idx, joint_idx[1:]):
        union(a, b)
    labels = np.fromiter((find(k) for k in range(n)), dtype=int, count=n)
    _, dense = np.unique(labels, return_inverse=True)
    return dense


def harmonic_posterior(
    nodes: Sequence[str],
    edges: Iterable[MessageEdge],
    boundary: Mapping[str, float],
    *,
    handle: int = 0,
    boundary_variance: Mapping[str, float] | None = None,
    unary: Mapping[str, tuple[float, float]] | None = None,
    unary_joint: tuple[Sequence[str], Sequence[float], np.ndarray] | None = None,
    screen: Mapping[str, float] | None = None,
    extra_precision: np.ndarray | None = None,
    strict_gauge: bool = False,
    no_support_variance: float = NO_SUPPORT_VARIANCE,
) -> HarmonicPosterior:
    """Solve the §7.5 layered system for ONE handle.

    ``boundary`` maps fresh-certified nodes to their innovations ``d_S``
    (§4.2 decides who qualifies — that is orchestration, not this solver);
    ``boundary_variance`` feeds the §7.4 ``Omega`` (omitted = certain).
    ``unary`` maps free nodes to independent ``(mean, variance)`` anchors;
    ``unary_joint = (nodes, means, covariance)`` is the D6 joint block —
    entries on boundary nodes are rejected (the boundary owns its value).
    ``screen`` maps free nodes to ``kappa >= 0`` (§7.6). ``extra_precision``
    is an optional PSD (N, N) hybrid term added over free indices."""
    names = list(nodes)
    index = {n: k for k, n in enumerate(names)}
    if len(index) != len(names):
        raise ValueError("duplicate node names")
    n = len(names)
    edge_rows = [(e, float(e.beta[handle])) for e in edges]

    if strict_gauge:
        for e, beta in edge_rows:
            if not (beta > 0.0) or not np.isfinite(beta):
                raise HarmonicGaugeError(
                    f"strict harmonic mode requires positive finite betas; "
                    f"{e.receiver!r}<-{e.informer!r} has beta {beta}"
                )
        flags = cycle_beta_products(names, [e for e, _ in edge_rows], handle=handle)
        if flags:
            worst = flags[0]
            raise HarmonicGaugeError(
                f"cycle-inconsistent betas (product {worst.product} at "
                f"{worst.receiver!r}<-{worst.informer!r}) — strict harmonic "
                "mode requires a gauge-consistent structure (§7.2)"
            )

    for name in boundary:
        if name not in index:
            raise ValueError(f"boundary references unknown node {name!r}")
    s_idx = sorted(index[name] for name in boundary)
    s_set = set(s_idx)
    d_by_idx = {index[name]: float(v) for name, v in boundary.items()}
    v_by_idx = {
        index[name]: float(v) for name, v in (boundary_variance or {}).items()
    }
    unary = dict(unary or {})
    for name in unary:
        if name not in index:
            raise ValueError(f"unary anchor references unknown node {name!r}")
    unary_idx = {
        index[name]: (float(m), float(v))
        for name, (m, v) in unary.items()
        if index[name] not in s_set  # boundary wins; §7.5
    }
    joint_idx: list[int] = []
    joint_mean = joint_cov = None
    if unary_joint is not None:
        j_nodes, j_means, j_cov = unary_joint
        joint_idx = [index[name] for name in j_nodes]
        if any(k in s_set for k in joint_idx):
            raise ValueError("joint unary block may not include boundary nodes")
        if set(joint_idx) & set(unary_idx):
            raise ValueError("node appears in both diagonal and joint unary blocks")
        joint_mean = np.asarray(j_means, dtype=float)
        joint_cov = np.asarray(j_cov, dtype=float)
        if joint_cov.shape != (len(joint_idx), len(joint_idx)):
            raise ValueError("joint unary covariance shape mismatch")
    kappa = np.zeros(n)
    for name, k in (screen or {}).items():
        if float(k) < 0.0:
            raise ValueError("screen kappa must be >= 0")
        kappa[index[name]] = float(k)

    component = _components(n, edge_rows, index, extra_precision, joint_idx)
    sources: list[tuple[str, str]] = [("boundary", names[i]) for i in s_idx]
    sources += [("unary", names[i]) for i in sorted(unary_idx)]
    sources += [("unary", names[i]) for i in joint_idx]
    src_col = {("boundary", i): c for c, i in enumerate(s_idx)}
    off = len(s_idx)
    for c, i in enumerate(sorted(unary_idx)):
        src_col[("unary", i)] = off + c
    off += len(unary_idx)
    for c, i in enumerate(joint_idx):
        src_col[("unary", i)] = off + c
    source_values = np.array(
        [d_by_idx[i] for i in s_idx]
        + [unary_idx[i][0] for i in sorted(unary_idx)]
        + ([] if joint_mean is None else list(joint_mean))
    )

    mean = np.zeros(n)
    variance = np.full(n, no_support_variance)
    covariance = np.zeros((n, n))
    gain = np.zeros((n, len(sources)))
    no_path = np.ones(n, dtype=bool)
    for i in s_idx:
        mean[i] = d_by_idx[i]
        variance[i] = v_by_idx.get(i, 0.0)
        covariance[i, i] = variance[i]
        gain[i, src_col[("boundary", i)]] = 1.0
        no_path[i] = False

    for label in range(component.max() + 1 if n else 0):
        comp = np.flatnonzero(component == label)
        f_idx = [int(i) for i in comp if i not in s_set]
        if not f_idx:
            continue
        cs = [int(i) for i in comp if i in s_set]
        c_unary = [i for i in f_idx if i in unary_idx]
        c_joint = [i for i in f_idx if i in joint_idx]
        if not cs and not c_unary and not c_joint:
            covariance[f_idx, f_idx] = no_support_variance  # §7.7: nothing invented
            continue
        local = {i: t for t, i in enumerate(f_idx)}
        c_edges = [
            (e, b) for e, b in edge_rows
            if index[e.receiver] in local
            or (b != 0.0 and index[e.informer] in local)
        ]
        b_f = np.zeros((len(c_edges), len(f_idx)))
        b_s = np.zeros((len(c_edges), len(cs)))
        s_local = {i: t for t, i in enumerate(cs)}
        prec = np.zeros(len(c_edges))
        for r, (e, b) in enumerate(c_edges):
            prec[r] = e.precision
            for node_i, coeff in ((index[e.receiver], 1.0), (index[e.informer], -b)):
                if node_i in local:
                    b_f[r, local[node_i]] += coeff
                elif node_i in s_local:
                    b_s[r, s_local[node_i]] += coeff
        omega = np.diag(1.0 / prec)
        if cs:
            v_s = np.array([v_by_idx.get(i, 0.0) for i in cs])
            if np.any(v_s > 0.0):
                omega = omega + b_s @ np.diag(v_s) @ b_s.T
        omega_inv_bf = np.linalg.solve(omega, b_f) if len(c_edges) else b_f
        a = b_f.T @ omega_inv_bf + np.diag(kappa[f_idx])
        b_vec = np.zeros(len(f_idx))
        if cs:
            d_s = np.array([d_by_idx[i] for i in cs])
            g_boundary = -(omega_inv_bf.T @ b_s)  # (n_F, n_S) pre-Sigma
            b_vec += g_boundary @ d_s
        for i in c_unary:
            m_u, v_u = unary_idx[i]
            if not (v_u > 0.0):
                raise ValueError("diagonal unary variance must be > 0")
            a[local[i], local[i]] += 1.0 / v_u
            b_vec[local[i]] += m_u / v_u
        if c_joint:
            r_joint = np.linalg.inv(joint_cov)
            h = np.zeros((len(joint_idx), len(f_idx)))
            for row, i in enumerate(joint_idx):
                h[row, local[i]] = 1.0
            a += h.T @ r_joint @ h
            b_vec += h.T @ r_joint @ joint_mean
        if extra_precision is not None:
            a += extra_precision[np.ix_(f_idx, f_idx)]
        try:
            np.linalg.cholesky(a)
        except np.linalg.LinAlgError as exc:
            raise np.linalg.LinAlgError(
                f"free component {[names[i] for i in f_idx[:6]]}... is not "
                "positive definite — check zero-beta structure or anchors"
            ) from exc
        sigma = np.linalg.inv(a)
        z = sigma @ b_vec
        mean[f_idx] = z
        variance[f_idx] = np.diag(sigma)
        covariance[np.ix_(f_idx, f_idx)] = sigma
        no_path[f_idx] = False
        if cs:
            g = sigma @ g_boundary
            for col_local, i in enumerate(cs):
                gain[f_idx, src_col[("boundary", i)]] = g[:, col_local]
        for i in c_unary:
            gain[f_idx, src_col[("unary", i)]] = (
                sigma[:, local[i]] / unary_idx[i][1]
            )
        if c_joint:
            g_j = sigma @ (h.T @ r_joint)
            for col_local, i in enumerate(joint_idx):
                gain[f_idx, src_col[("unary", i)]] = g_j[:, col_local]

    return HarmonicPosterior(
        nodes=tuple(names), handle=handle, mean=mean, variance=variance,
        posterior_covariance=covariance, boundary=np.array(s_idx, dtype=int),
        no_active_observation_path=no_path, component=component,
        sources=tuple(sources), source_values=source_values, gain=gain,
    )
