"""Layered-mode preflight sweeps (P6 V3) — the dynamic-harmonic additions to
POST /graph/preflight, split out of graph_preflight.py (size policy).

Same DRY-RUN contract: nothing is fitted, solved, or recorded. The checks
read the effective relation rows (with the resolved semantics), the persisted
residual store, and the reference date only:

* ``directed_cycle``  (BLOCKER) — the layered solve REJECTS directed cycles
  (framework §6.5), so Run would fail outright.
* ``no_support``      (warning) — directed-aware reachability (§7.7): a
  directed arc transmits source→target ONLY, so the undirected §14.3 sweep
  would claim support where none exists. Stored residuals count as support
  (the D7 ghost prediction anchors the node).
* ``residual_config_mismatch`` (warning) — store entries built under a
  different relation config are PURGED at Run (golden 15.13).
* ``stale_residual``  (warning/info) — residual memory far beyond its
  half-life carries ~nothing (info); under the random-walk policy old
  dislocations never decay at all (warning).
"""

from __future__ import annotations

from collections import deque

from volfit.api.graph_dynamic import (
    _config_version,
    _directed_from_rows,
    row_semantics,
)
from volfit.api.schemas import GraphPreflightIssue

#: A random-walk (no half-life) residual older than this many days is loud.
RW_STALE_DAYS = 30.0
#: With a half-life H, memory older than this many H's is effectively gone.
DECAYED_HALF_LIVES = 3.0


def _issue(severity: str, code: str, message: str, count: int = 1) -> GraphPreflightIssue:
    return GraphPreflightIssue(severity=severity, code=code, message=message, count=count)


def dynamic_issues(
    state,
    request,
    names: list,
    index: dict,
    rows,
    observed: set[int],
    issues: list[GraphPreflightIssue],
) -> None:
    """Append the layered-mode findings. ``rows`` is the effective SCHEMA row
    list (request > persisted), or None/empty for the auto relations (all
    reciprocal). ``request`` must already be policy-resolved. Replaces the
    generic §14.3 connectivity sweep (the caller skips it in layered mode)."""
    sem = request.relationSemanticsDefaults
    row_list = list(rows or [])
    directed_rows = [
        r
        for r in row_list
        if row_semantics(r, sem) == "directed_state"
        and (r.sourceTicker, r.sourceExpiry) in index
        and (r.targetTicker, r.targetExpiry) in index
    ]
    reciprocal_rows = [
        r for r in row_list if row_semantics(r, sem) == "reciprocal_harmonic"
    ]

    # ---- directed cycles: Kahn over the directed arcs (blocker — §6.5).
    arcs = [
        (
            index[(r.sourceTicker, r.sourceExpiry)],
            index[(r.targetTicker, r.targetExpiry)],
        )
        for r in directed_rows
    ]
    indeg = dict.fromkeys(range(len(names)), 0)
    out: dict[int, list[int]] = {}
    for s, t in arcs:
        indeg[t] += 1
        out.setdefault(s, []).append(t)
    queue = deque(i for i in range(len(names)) if indeg[i] == 0)
    seen = 0
    while queue:
        i = queue.popleft()
        seen += 1
        for j in out.get(i, []):
            indeg[j] -= 1
            if indeg[j] == 0:
                queue.append(j)
    cyclic = len(names) - seen
    if cyclic > 0:
        issues.append(
            _issue(
                "blocker",
                "directed_cycle",
                f"{cyclic} node(s) sit on a DIRECTED relation cycle — the "
                "layered solve rejects cycles (§6.5). Model reciprocity with "
                "reciprocal semantics instead.",
                count=cyclic,
            )
        )

    # ---- residual store sweeps (config identity + staleness).
    store = getattr(state, "graph_dynamic_residuals", None) or {}
    in_universe = {name: st for name, st in store.items() if name in index}
    if in_universe:
        current = _config_version(_directed_from_rows(directed_rows, request), request)
        mismatched = [
            name
            for name, st in in_universe.items()
            if st.config_version and st.config_version != current
        ]
        if mismatched:
            issues.append(
                _issue(
                    "warning",
                    "residual_config_mismatch",
                    f"{len(mismatched)} stored residual(s) carry a different "
                    "relation-config version — Run will PURGE that temporal "
                    "memory (golden 15.13).",
                    count=len(mismatched),
                )
            )
        now_day = float(state.reference_date.toordinal())
        half_life = request.residualHalfLifeDays
        ages = [
            now_day - st.observed_at
            for st in in_universe.values()
            if st.observed_at is not None
        ]
        if half_life:
            decayed = [a for a in ages if a > DECAYED_HALF_LIVES * half_life]
            if decayed:
                issues.append(
                    _issue(
                        "info",
                        "stale_residual",
                        f"{len(decayed)} stored residual(s) older than "
                        f"{DECAYED_HALF_LIVES:g}× the {half_life:g}d half-life "
                        "— effectively decayed; they contribute ~nothing.",
                        count=len(decayed),
                    )
                )
        else:
            old = [a for a in ages if a > RW_STALE_DAYS]
            if old:
                issues.append(
                    _issue(
                        "warning",
                        "stale_residual",
                        f"{len(old)} stored residual(s) older than "
                        f"{RW_STALE_DAYS:g}d under the random-walk policy (no "
                        "half-life) — old dislocations never decay; consider "
                        "a half-life in the config policy.",
                        count=len(old),
                    )
                )

    # ---- directed-aware support (§7.7; replaces the undirected §14.3 sweep).
    if not observed:
        return  # the no-observation warning already covers the whole field
    adjacency: dict[int, list[int]] = {}

    def _link(a: int, b: int) -> None:
        adjacency.setdefault(a, []).append(b)

    if row_list:
        for r in reciprocal_rows:
            s = index.get((r.sourceTicker, r.sourceExpiry))
            t = index.get((r.targetTicker, r.targetExpiry))
            if s is not None and t is not None:
                _link(s, t)
                _link(t, s)
        for s, t in arcs:
            _link(s, t)  # a directed arc transmits source→target ONLY
    else:
        # Auto relations: calendar ladders + same-expiry cross pairs, all
        # reciprocal. Rebuilding them here would re-derive maturities, so use
        # the structural equivalent: every same-ticker pair (the ladder is a
        # connected chain) and every same-expiry pair.
        by_ticker: dict[str, list[int]] = {}
        by_expiry: dict[str, list[int]] = {}
        for name, i in index.items():
            by_ticker.setdefault(name[0], []).append(i)
            by_expiry.setdefault(name[1], []).append(i)
        for group in list(by_ticker.values()) + list(by_expiry.values()):
            for a, b in zip(group, group[1:]):
                _link(a, b)
                _link(b, a)

    seeds = set(observed)
    # D7 ghosts: a stored residual predicts its node even with no parents.
    seeds.update(index[name] for name in in_universe)
    reached = set(seeds)
    frontier = deque(seeds)
    while frontier:
        i = frontier.popleft()
        for j in adjacency.get(i, []):
            if j not in reached:
                reached.add(j)
                frontier.append(j)
    unsupported = len(names) - len(reached)
    if unsupported > 0:
        issues.append(
            _issue(
                "warning",
                "no_support",
                f"{unsupported} node(s) have no boundary, anchor or residual "
                "support — directed arcs transmit one way only; they stay at "
                "their transported prior with broad uncertainty (§7.7).",
                count=unsupported,
            )
        )
