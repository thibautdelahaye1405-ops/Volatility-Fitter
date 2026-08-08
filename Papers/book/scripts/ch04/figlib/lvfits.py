"""The chapter's local-volatility fitting protocol (frozen data + synthetics).

Real-chain protocol (stated in the chapter appendix): per underlier, one
P1 local-variance sheet is calibrated by the reference implementation to the
frozen snapshot's prepared mid quotes of ALL expiries at once --
  * vertex grid: maturity rows at 0 and every quoted expiry; strike columns
    delta-spaced by the longest expiry's ATM width, hull-extended to the
    pooled quoted range, with an even-gap coverage rule guaranteeing every
    expiry at least M_MIN columns inside its own traded range;
  * PDE lattice: strike step min(0.01, 0.15 sigma sqrt(tau_min)) capped at
    N_CAP nodes, y = 1 a node; every expiry a time node, every interval at
    least 8 implicit steps and steps no larger than 0.01;
  * objective: vega-scaled mid residuals, spacing-aware curvature roughness
    lambda = 1e-2 toward the flat reference, front tie 1e-2; box bounds
    adaptive in the observed vol range; trust-region least squares.

Synthetic protocol: a smooth skewed truth priced through the independent
dense marcher (pde1d), quoted at four expiries, and fitted on a fixed
5 x 10 vertex sheet with lambda = 1e-4 (the recovery/identifiability
running example).  Everything is deterministic: no randomness anywhere
(the 'noise' is an alternating +/- ripple).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.special import ndtri

import data4
import pde1d
from volfit.core.black import black_call, black_vega_sigma, implied_vol
from volfit.models.localvol.affine import AffineVarianceSurface, solve_affine_dupire
from volfit.models.localvol.affine_calib import OptionQuote, calibrate_affine

# ---------------------------------------------------------------- protocol
PUT_DELTAS = (0.01, 0.02, 0.05, 0.10, 0.25, 0.40)  # and call mirrors + ATM
M_MIN = 6          # per-expiry coverage floor (columns inside the traded range)
N_CAP = 800        # PDE strike-node cap
DX_FRAC = 0.15     # PDE strike step as a fraction of the shortest ATM width
DT_MAX = 0.01      # PDE time-step ceiling
NT_MIN = 8         # minimum implicit steps per maturity interval
REG_LAMBDA = 1e-2  # roughness weight (one convention, real and synthetic)
REG_LAMBDA_SYN = 1e-2
FRONT_TIE = 1e-2   # front-tie weight
VEGA_FLOOR = 1e-3  # vega floor inside the residual scale (Ch. 2's eta)


# ------------------------------------------------------------ grid builders
def atm_vol(n: data4.Node) -> float:
    """Mid implied vol at k = 0 (linear interpolation on the quote strip)."""
    order = np.argsort(n.k)
    return float(np.interp(0.0, n.k[order], n.iv_mid[order]))


def vertex_grid(nodes: list[data4.Node]) -> tuple[np.ndarray, np.ndarray]:
    """(t_nodes, y_nodes) of the P1 sheet under the chapter's protocol."""
    longest = nodes[-1]
    scale = atm_vol(longest) * np.sqrt(longest.t)
    z = np.array(sorted({ndtri(d) for d in PUT_DELTAS}
                        | {0.0} | {-ndtri(d) for d in PUT_DELTAS}))
    y = np.exp(scale * z)
    # hull extension: no quote may fall outside the vertex hull
    y_lo = min(float(np.exp(n.k.min())) for n in nodes)
    y_hi = max(float(np.exp(n.k.max())) for n in nodes)
    y[0] = min(y[0], 0.995 * y_lo)
    y[-1] = max(y[-1], 1.005 * y_hi)
    cols = set(np.round(y, 10))
    # even-gap coverage: every expiry owns >= M_MIN columns inside its own
    # traded range, spread evenly (split the widest boundary-augmented gap
    # until none exceeds range/(M_MIN - 1)).
    for n in nodes:
        lo, hi = float(np.exp(n.k.min())), float(np.exp(n.k.max()))
        target = (hi - lo) / (M_MIN - 1)
        while True:
            inside = sorted(c for c in cols if lo <= c <= hi)
            pts = np.array([lo] + inside + [hi])
            gaps = np.diff(pts)
            j = int(np.argmax(gaps))
            if gaps[j] <= target + 1e-12:
                break
            cols.add(round(0.5 * (pts[j] + pts[j + 1]), 10))
    t_nodes = np.array([0.0] + [n.t for n in nodes])
    return t_nodes, np.array(sorted(cols))


def pde_grids(nodes: list[data4.Node], y_nodes: np.ndarray,
              refine: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """(y_grid, t_grid) of the lattice; ``refine`` > 1 is the refined operator
    (strike step / refine, time steps x refine^2 -- e.g. refine=2 gives
    dy/2 and 4x the steps)."""
    width = min(atm_vol(n) * np.sqrt(n.t) for n in nodes)
    y_max = max(2.5, 1.05 * float(y_nodes[-1]))
    dy = max(min(0.01, DX_FRAC * width), y_max / N_CAP) / refine
    n_lo = int(np.ceil(1.0 / dy))
    n_hi = int(np.ceil((y_max - 1.0) / dy))
    y_grid = np.unique(np.concatenate(
        [np.linspace(0.0, 1.0, n_lo + 1), np.linspace(1.0, y_max, n_hi + 1)]))
    ts = [0.0]
    prev = 0.0
    for n in nodes:
        steps = max(NT_MIN, int(np.ceil((n.t - prev) / DT_MAX))) * refine * refine
        ts.extend(np.linspace(prev, n.t, steps + 1)[1:])
        prev = n.t
    return y_grid, np.array(ts)


def quote_list(nodes: list[data4.Node]) -> list[OptionQuote]:
    """Vega-scaled normalized-call mid quotes for the whole surface."""
    out: list[OptionQuote] = []
    for n in nodes:
        prices = black_call(n.k, n.w_mid)
        vega = black_vega_sigma(n.k, n.iv_mid, n.t)
        for k, p, vg in zip(n.k, np.atleast_1d(prices), np.atleast_1d(vega)):
            out.append(OptionQuote(
                t=n.t, x=float(np.exp(k)), price=float(p),
                tol=0.01 * max(float(vg), VEGA_FLOOR)))
    return out


# ------------------------------------------------------------- real chains
@dataclass
class SurfaceFit:
    """One calibrated sheet plus everything the figures read off it."""

    ticker: str
    nodes: list[data4.Node]
    surface: AffineVarianceSurface
    y_grid: np.ndarray
    t_grid: np.ndarray
    quotes: list[OptionQuote]
    n_evals: int
    iv_model: list[np.ndarray]      # in-operator model IVs per node
    iv_refined: list[np.ndarray]    # refined-operator model IVs per node

    def rms_bp(self, refined: bool = False) -> float:
        errs = np.concatenate([
            1e4 * (iv - n.iv_mid) for iv, n in
            zip(self.iv_refined if refined else self.iv_model, self.nodes)])
        return float(np.sqrt(np.mean(errs**2)))

    def per_expiry_rms_bp(self, refined: bool = False) -> np.ndarray:
        return np.array([
            float(np.sqrt(np.mean((1e4 * (iv - n.iv_mid))**2))) for iv, n in
            zip(self.iv_refined if refined else self.iv_model, self.nodes)])


def _model_ivs(surface: AffineVarianceSurface, nodes: list[data4.Node],
               y_grid: np.ndarray, t_grid: np.ndarray) -> list[np.ndarray]:
    """Model IVs at every quote of every node from ONE solve on the grids."""
    sol = solve_affine_dupire(surface, y_grid, t_grid, [n.t for n in nodes])
    out = []
    for i, n in enumerate(nodes):
        prices = sol.price_at(i, np.exp(n.k))
        out.append(np.asarray(implied_vol(n.k, prices, n.t), dtype=float))
    return out


@lru_cache(maxsize=None)
def fit_ticker(ticker: str) -> SurfaceFit:
    """The chapter's calibrated sheet for one underlier (cached)."""
    nodes = data4.nodes(ticker)
    t_nodes, y_nodes = vertex_grid(nodes)
    y_grid, t_grid = pde_grids(nodes, y_nodes)
    quotes = quote_list(nodes)
    sig_atm = np.array([atm_vol(n) for n in nodes])
    sig_max = max(float(n.iv_mid.max()) for n in nodes)
    v_lo = min(0.0025, (0.5 * float(sig_atm.min())) ** 2)
    v_hi = min(max(0.36, (3.0 * sig_max) ** 2), 16.0)
    theta0 = np.full((t_nodes.size, y_nodes.size),
                     float(np.median(sig_atm)) ** 2)
    surface0 = AffineVarianceSurface(t_nodes, y_nodes, theta0)
    calib = calibrate_affine(
        surface0, quotes, y_grid, t_grid,
        bounds=(v_lo, v_hi), reg_lambda=REG_LAMBDA, reg_rho=1.0,
        reg_nodes=(t_nodes, y_nodes), front_tie_weight=FRONT_TIE,
        engine="banded", stall_window=0, max_nfev=200,
    )
    iv_model = _model_ivs(calib.surface, nodes, y_grid, t_grid)
    y2, t2 = pde_grids(nodes, y_nodes, refine=2)
    iv_refined = _model_ivs(calib.surface, nodes, y2, t2)
    return SurfaceFit(ticker, nodes, calib.surface, y_grid, t_grid, quotes,
                      calib.n_evals, iv_model, iv_refined)


# --------------------------------------------------------------- synthetic
SYN_T = (0.10, 0.25, 0.50, 1.00)
SYN_SIGMA0 = 0.24          # strike-placement scale of the synthetic quotes
SYN_N_STRIKES = 31
SYN_Z_SPAN = 2.2
SYN_DEEP_COL = 0.45        # the unquoted deep-put vertex column


def sigma_true(tau, y):
    """The smooth skewed synthetic truth (local VOL, not variance)."""
    tau = np.asarray(tau, dtype=float)
    y = np.asarray(y, dtype=float)
    return 0.21 - 0.10 * np.tanh((y - 1.0) / 0.22) + 0.03 * np.exp(-2.0 * tau)


def v_true(tau, y):
    return sigma_true(tau, y) ** 2


@lru_cache(maxsize=1)
def truth_prices() -> tuple[np.ndarray, dict[float, np.ndarray]]:
    """(y_dense, {T: c(T, .)}) from the independent dense marcher."""
    y = pde1d.uniform_grid(3.0, 0.0025)
    t_grid = np.linspace(0.0, 1.0, 501)   # every SYN_T is a grid point
    return y, pde1d.march(v_true, y, t_grid, snapshots=list(SYN_T))


def syn_quotes(ripple_bp: float = 0.0,
               n_strikes: int = SYN_N_STRIKES) -> list[dict]:
    """Per-expiry synthetic quote strips (k, iv, y), optionally rippled.

    The 'noise' is a deterministic alternating +/- ``ripple_bp`` vol ripple
    -- a stylized bid-ask bounce, no randomness.
    """
    y_dense, prices = truth_prices()
    strips = []
    for t in SYN_T:
        z = np.linspace(-SYN_Z_SPAN, SYN_Z_SPAN, n_strikes)
        k = z * SYN_SIGMA0 * np.sqrt(t)
        p = np.interp(np.exp(k), y_dense, prices[t])
        iv = np.asarray(implied_vol(k, p, t), dtype=float)
        iv = iv + 1e-4 * ripple_bp * (-1.0) ** np.arange(k.size)
        strips.append({"t": t, "k": k, "y": np.exp(k), "iv": iv})
    return strips


def syn_vertex_grid() -> tuple[np.ndarray, np.ndarray]:
    z = np.array(sorted({ndtri(d) for d in (0.02, 0.10, 0.25, 0.40)}
                        | {0.0} | {-ndtri(d) for d in (0.02, 0.10, 0.25, 0.40)}))
    y = np.exp(SYN_SIGMA0 * z)
    y = np.array(sorted(set(np.round(y, 10)) | {SYN_DEEP_COL}))
    return np.array([0.0] + list(SYN_T)), y


def syn_pde_grids() -> tuple[np.ndarray, np.ndarray]:
    dy = 0.005
    n_lo, n_hi = 200, 400
    y_grid = np.unique(np.concatenate(
        [np.linspace(0.0, 1.0, n_lo + 1), np.linspace(1.0, 3.0, n_hi + 1)]))
    ts = [0.0]
    prev = 0.0
    for t in SYN_T:
        steps = max(NT_MIN, int(np.ceil((t - prev) / DT_MAX)))
        ts.extend(np.linspace(prev, t, steps + 1)[1:])
        prev = t
    assert abs(y_grid[200] - 1.0) < 1e-12 and dy > 0
    return y_grid, np.array(ts)


@dataclass
class SynFit:
    surface: AffineVarianceSurface
    y_grid: np.ndarray
    t_grid: np.ndarray
    strips: list[dict]
    n_evals: int
    iv_model: list[np.ndarray]

    def quote_err_bp(self) -> np.ndarray:
        return np.concatenate([
            1e4 * (iv - s["iv"]) for iv, s in zip(self.iv_model, self.strips)])


@lru_cache(maxsize=None)
def syn_fit(ripple_bp: float = 0.0) -> SynFit:
    """The synthetic running example fitted from a flat seed (cached)."""
    strips = syn_quotes(ripple_bp)
    t_nodes, y_nodes = syn_vertex_grid()
    y_grid, t_grid = syn_pde_grids()
    quotes = []
    for s in strips:
        w = s["iv"] ** 2 * s["t"]
        prices = black_call(s["k"], w)
        vega = black_vega_sigma(s["k"], s["iv"], s["t"])
        for k, p, vg in zip(s["k"], np.atleast_1d(prices), np.atleast_1d(vega)):
            quotes.append(OptionQuote(
                t=s["t"], x=float(np.exp(k)), price=float(p),
                tol=0.01 * max(float(vg), VEGA_FLOOR)))
    theta0 = np.full((t_nodes.size, y_nodes.size), SYN_SIGMA0**2)
    surface0 = AffineVarianceSurface(t_nodes, y_nodes, theta0)
    calib = calibrate_affine(
        surface0, quotes, y_grid, t_grid,
        bounds=(0.005, 0.36), reg_lambda=REG_LAMBDA_SYN, reg_rho=1.0,
        reg_nodes=(t_nodes, y_nodes), front_tie_weight=1.0,
        engine="banded", stall_window=0, max_nfev=200,
    )
    sol = solve_affine_dupire(calib.surface, y_grid, t_grid, list(SYN_T))
    iv_model = []
    for i, s in enumerate(strips):
        p = sol.price_at(i, s["y"])
        iv_model.append(np.asarray(implied_vol(s["k"], p, s["t"]), dtype=float))
    return SynFit(calib.surface, y_grid, t_grid, strips, calib.n_evals, iv_model)


def syn_surface_error(fit: SynFit) -> tuple[float, float]:
    """(rms, max) |sigma_fit - sigma_true| in vol POINTS on the quote-covered
    region: tau in [T1, T4], k inside the (tau-interpolated) quoted span."""
    taus = np.linspace(SYN_T[0], SYN_T[-1], 61)
    k_lo = np.interp(taus, [s["t"] for s in fit.strips],
                     [s["k"].min() for s in fit.strips])
    k_hi = np.interp(taus, [s["t"] for s in fit.strips],
                     [s["k"].max() for s in fit.strips])
    errs = []
    for tau, lo, hi in zip(taus, k_lo, k_hi):
        y = np.exp(np.linspace(lo, hi, 81))
        sig_fit = np.sqrt(fit.surface.variance(y, float(tau)))
        errs.append(100.0 * np.abs(sig_fit - sigma_true(tau, y)))
    errs = np.concatenate(errs)
    return float(np.sqrt(np.mean(errs**2))), float(errs.max())
