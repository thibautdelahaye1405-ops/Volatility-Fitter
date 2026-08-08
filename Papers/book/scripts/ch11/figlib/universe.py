"""The chapter's staged universe, built FROM the frozen snapshot.

Twenty nodes: the frozen SPY and NVDA boards (the six expiries of 18 days
and beyond -- the two sub-week nodes live on Chapter 8's event clock and are
excluded with that stated reason) plus two synthetic names built by stated
recipes -- "sister" (beside the mega-cap) and "blend" (between the boards),
four middle expiries each.

The morning is constructed BACKWARD from the real data so that the truth at
every dark real node is the actual frozen board.  A stated systematic
repricing (constant total-variance injection from the SPY December anchor,
scaled per name by its stated beta), one seeded idiosyncratic scatter draw
(the construction's only randomness), and a carried dislocation on the
sister name define the true innovation field Theta*; yesterday's handles
are today's true handles MINUS Theta*; the solver sees yesterday (the
baselines), the lit observations (Theta* plus stated observation noise at
the lit nodes), and the desk's asserted contracts, whose stated relation
noise is exactly the construction's own scatter, propagated.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2]
for _sub in ("ch09", "ch03"):
    _p = str(_SCRIPTS / _sub / "figlib")
    if _p not in sys.path:
        sys.path.append(_p)  # append: ch11's own figlib keeps priority

import data3  # noqa: E402  (Chapter 3's frozen-snapshot loader)
import data9  # noqa: E402  (Chapter 9's stored-fit smiles)

# ----------------------------------------------------------- the universe
EXPIRIES = ["2026-08-21", "2026-09-18", "2026-12-18", "2027-03-19",
            "2027-09-17", "2027-12-17"]
SYN_EXPIRIES = EXPIRIES[1:5]          # the four middle expiries
ANCHOR_EXPIRY = "2026-12-18"          # the SPY December anchor node

NAMES = ["SPY", "NVDA", "sister", "blend"]
REAL = {"SPY": EXPIRIES, "NVDA": EXPIRIES}
SYN = {"sister": SYN_EXPIRIES, "blend": SYN_EXPIRIES}

# Stated construction parameters (all disclosed in the chapter appendix).
ANCHOR_MOVE = 0.80        # vol points at SPY December
TRUE_BETA = {"SPY": 1.0, "NVDA": 1.6, "sister": 1.44, "blend": 1.2}
SCATTER_SD = 0.30         # per-node idiosyncratic scatter, vol points
OBS_SD = 0.10             # lit observation noise, vol points
SEED = 11711              # the chapter's only randomness

# The sister's carried dislocation (the residual state).
U_PRINT = -0.90           # measured at yesterday's 15:50 print, vol points
DT_DAYS = 0.75            # elapsed to this morning, days
HALF_LIFE = 2.0           # the stated half-life, days
U_GROWTH_SD = 0.20        # residual process growth since the print, vol pts

# Asserted cross relations (receiver <- informer, amplitude).
CROSS = [
    ("NVDA", "SPY", 1.6),
    ("sister", "NVDA", 0.9),
    ("blend", "SPY", 1.2),
]

# Lit this morning: the whole index board plus two mega-cap nodes.
LIT = [("SPY", e) for e in EXPIRIES] + [
    ("NVDA", "2026-09-18"), ("NVDA", "2027-03-19"),
]

OVERTRUST = 25.0          # the dishonest arm: edge precisions x 25


@dataclass(frozen=True)
class UNode:
    """One universe node: identity, maturity, and its handle bookkeeping."""

    name: str
    expiry: str
    tau: float
    level: float        # today's TRUE ATM level, vol points (sigma * 100)
    theta_true: float   # the true innovation, vol points
    lit: bool

    @property
    def baseline(self) -> float:
        """Yesterday's level = today's truth minus the true innovation."""
        return self.level - self.theta_true

    @property
    def label(self) -> str:
        return f"{self.name} {self.expiry[2:]}"


def u_carried() -> float:
    """The carried residual mean this morning."""
    return float(U_PRINT * 2.0 ** (-DT_DAYS / HALF_LIFE))


@lru_cache(maxsize=1)
def taus() -> dict[str, float]:
    return {e: data3.node("SPY", e).t for e in EXPIRIES}


@lru_cache(maxsize=1)
def real_levels() -> dict[tuple[str, str], float]:
    """True ATM levels of the sixteen real nodes, in vol points."""
    out = {}
    for name in ("SPY", "NVDA"):
        for e in EXPIRIES:
            out[(name, e)] = 100.0 * data9.smile(name, e).atm_vol
    return out


def _recipe_level(name: str, expiry: str) -> float:
    """The synthetic names' stated recipes (today's true levels)."""
    lv = real_levels()
    if name == "sister":
        return lv[("NVDA", expiry)] - 2.0
    if name == "blend":
        return 0.5 * lv[("SPY", expiry)] + 0.5 * lv[("NVDA", expiry)] + 0.5
    raise KeyError(name)


@lru_cache(maxsize=1)
def build() -> list[UNode]:
    """The twenty nodes with their constructed morning."""
    rng = np.random.default_rng(SEED)
    tau = taus()
    tau_anchor = tau[ANCHOR_EXPIRY]
    nodes: list[UNode] = []
    boards = [("SPY", EXPIRIES), ("NVDA", EXPIRIES),
              ("sister", SYN_EXPIRIES), ("blend", SYN_EXPIRIES)]
    for name, exps in boards:
        for e in exps:
            systematic = TRUE_BETA[name] * ANCHOR_MOVE * tau_anchor / tau[e]
            idio = float(rng.normal(0.0, SCATTER_SD))
            theta = systematic + idio
            if name == "sister":
                theta += u_carried()
            level = (real_levels()[(name, e)] if name in ("SPY", "NVDA")
                     else _recipe_level(name, e))
            nodes.append(UNode(
                name=name, expiry=e, tau=tau[e], level=level,
                theta_true=theta, lit=(name, e) in LIT,
            ))
    return nodes


def index_of() -> dict[tuple[str, str], int]:
    return {(n.name, n.expiry): i for i, n in enumerate(build())}


@lru_cache(maxsize=1)
def observations() -> dict[tuple[str, str], float]:
    """The lit measured innovations: truth plus seeded observation noise."""
    rng = np.random.default_rng(SEED + 1)
    nodes = build()
    return {
        (n.name, n.expiry): n.theta_true + float(rng.normal(0.0, OBS_SD))
        for n in nodes if n.lit
    }


def relation_var(beta: float, extra: float = 0.0) -> float:
    """Stated relation variance: the scatter of both ends, propagated."""
    return SCATTER_SD**2 * (1.0 + beta**2) + extra


def problem(trust_scale: float = 1.0):
    """The morning's solve as a solver.Problem (honest arm at scale 1)."""
    import solver

    nodes = build()
    idx = index_of()
    prob = solver.Problem(n=len(nodes))
    tau = taus()
    uc = u_carried()
    # Calendar chains: canonical receiver = the shorter maturity.
    for name, exps in (("SPY", EXPIRIES), ("NVDA", EXPIRIES),
                       ("sister", SYN_EXPIRIES), ("blend", SYN_EXPIRIES)):
        for e_short, e_long in zip(exps[:-1], exps[1:]):
            beta = tau[e_long] / tau[e_short]
            p = trust_scale / relation_var(beta)
            prob.edge(idx[(name, e_short)], idx[(name, e_long)], p, beta)
    # Cross relations at shared expiries; the sister's carry the residual
    # mean as the contract offset, and its grown variance widens the noise.
    for recv, inf, beta in CROSS:
        for e in (SYN_EXPIRIES if recv in SYN else EXPIRIES):
            extra = U_GROWTH_SD**2 if recv == "sister" else 0.0
            p = trust_scale / relation_var(beta, extra)
            offset = uc if recv == "sister" else 0.0
            prob.edge(idx[(recv, e)], idx[(inf, e)], p, beta, offset)
    # Lit observations (the construction's baselines are exact, so the
    # baseline-variance term of the chapter's eq. (grobs) is zero here).
    for key, value in observations().items():
        prob.observe(idx[key], value, OBS_SD**2)
    return prob


def solve_morning(trust_scale: float = 1.0):
    import solver

    return solver.solve(problem(trust_scale))


def audit_std(post) -> float:
    """std of the standardized dark-node errors (the chapter's audit)."""
    nodes = build()
    z = [(n.theta_true - post.mean[i]) / np.sqrt(post.var[i])
         for i, n in enumerate(nodes) if not n.lit]
    return float(np.std(z, ddof=0))


def dark_errors(post) -> list[tuple["UNode", float, float, float]]:
    """(node, graph error, baseline error, posterior sd) per dark node."""
    nodes = build()
    out = []
    for i, n in enumerate(nodes):
        if n.lit:
            continue
        out.append((n, float(post.mean[i] - n.theta_true),
                    float(-n.theta_true), float(np.sqrt(post.var[i]))))
    return out
