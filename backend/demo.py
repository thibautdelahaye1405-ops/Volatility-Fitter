"""End-to-end console demo of the vol-fitter engine in its current state.

Run from the repo root:
    .venv\\Scripts\\python backend\\demo.py

Walks through: synthetic market data -> implied forwards -> LQD slice
calibration -> calendar-constrained surface -> graph extrapolation of a vol
shock across a smile universe, printing the diagnostics a desk would look at.
"""

from datetime import date

import numpy as np

from volfit.calib import ExpiryQuotes, calibrate_surface
from volfit.data.forwards import implied_forwards
from volfit.data.provider import SyntheticProvider
from volfit.graph import build_increment_prior
from volfit.graph.smile_universe import (
    SmileNode,
    build_universe,
    propagate_handles,
    reconstruct_smiles,
)
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import LQDParams, endpoint_scales, lee_slopes
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.quadrature import build_slice
from volfit.models.svi_jw import RawSVI

LINE = "-" * 64


def section(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


# ----------------------------------------------------------------- market data
section("1. Synthetic market snapshot (offline data layer)")
provider = SyntheticProvider(reference_date=date(2026, 6, 10))
snapshot = provider.fetch_chain("SPX")
print(f"ticker {snapshot.ticker}, spot {snapshot.spot:.2f}, "
      f"{len(snapshot.quotes)} quotes, expiries: "
      f"{[e.isoformat() for e in snapshot.expiries()]}")

forwards = implied_forwards(snapshot)
for expiry, fwd in list(forwards.items())[:2]:
    print(f"  {expiry}  implied forward {fwd.forward:9.2f}  "
          f"(parity regression on {fwd.n_strikes} strikes, rms {fwd.residual_rms:.2e})")

# ------------------------------------------------------------ slice calibration
section("2. LQD slice calibration (SPX-like SVI target, T = 0.5y)")
svi = RawSVI(a=0.010625, b=0.0728868987, rho=-0.5, m=0.0583095189, sigma=0.1009950494)
t = 0.5
k = np.linspace(-0.35, 0.30, 60)
result = calibrate_slice(k, svi.total_variance(k), t=t)
a_l, a_r = endpoint_scales(result.params)
beta_l, beta_r = lee_slopes(result.params)
handles = atm_handles(result.slice, t)
print(f"max IV error      {result.max_iv_error * 1e4:6.2f} vol bp "
      f"({result.n_evaluations} objective evaluations)")
print(f"ATM vol/skew/curv {handles.sigma0:.4f} / {handles.skew:.4f} / {handles.curvature:.4f}")
print(f"tails A_L, A_R    {a_l:.4f}, {a_r:.4f}   Lee slopes {beta_l:.4f}, {beta_r:.4f}")
print(f"martingale check  {result.slice.martingale_check():.12f}")
print(f"var-swap strike   {np.sqrt(result.slice.var_swap_strike() / t):.4%}")

# ----------------------------------------------------------- surface + calendar
section("3. Calendar-constrained surface (0.5y and 1.0y)")
surface = calibrate_surface(
    [
        ExpiryQuotes(t=0.5, k=k, w=svi.total_variance(k)),
        ExpiryQuotes(t=1.0, k=k, w=2.0 * svi.total_variance(k)),
    ],
    enforce_calendar=True,
)
for t_i, res, viol in zip(surface.expiries, surface.results, surface.calendar_residuals):
    print(f"  T={t_i:.2f}  max IV err {res.max_iv_error * 1e4:5.2f} bp   "
          f"calendar violation {viol:.2e}")

# --------------------------------------------------------- graph extrapolation
section("4. Graph extrapolation: 2 tickers x 3 expiries, 1 observed smile")
expiries = (0.25, 0.5, 1.0)
smiles = [SmileNode(name=(tk, te), t=te, params=result.params)
          for tk in ("AAA", "BBB") for te in expiries]
weights = {}
for tk in ("AAA", "BBB"):
    for t_near, t_far in zip(expiries[:-1], expiries[1:]):
        weights[((tk, t_near), (tk, t_far))] = 10.0
        weights[((tk, t_far), (tk, t_near))] = 10.0
for te in expiries:
    weights[(("AAA", te), ("BBB", te))] = 2.0
    weights[(("BBB", te), ("AAA", te))] = 2.0

universe = build_universe(smiles, weights)
priors = [build_increment_prior(universe.graph, kappa=1.0 / s**2, eta=eta)
          for s, eta in ((0.03, 2.0e4), (0.05, 7.0e3), (0.5, 70.0))]

observed = ("AAA", 0.5)
i_obs = universe.node_index(observed)
shock = universe.handles[i_obs] + np.array([0.02, 0.0, 0.0])  # AAA vol +2 pts
field = propagate_handles(universe, priors, {observed: shock},
                          baseline_precision=np.array([1e6, 1e6, 1e4]),
                          observation_precision=np.array([1e6, 1e6, 1e4]))

print("observed: AAA 0.5y ATM vol +2.00 pts; everything else extrapolated\n")
print(f"{'node':>12} {'base vol':>9} {'post vol':>9} {'shift bp':>9} {'95% band':>17}")
lo, hi = field.atm_vol_band()
for j, node in enumerate(universe.smiles):
    shift_bp = (field.mean[j, 0] - universe.handles[j, 0]) * 1e4
    tag = " <- observed" if node.name == observed else ""
    print(f"{str(node.name):>12} {universe.handles[j, 0]:9.4f} {field.mean[j, 0]:9.4f} "
          f"{shift_bp:9.1f} [{lo[j]:7.4f}, {hi[j]:7.4f}]{tag}")

rebuilt = reconstruct_smiles(universe, field, nodes=[("AAA", 1.0), ("BBB", 1.0)])
print("\nreconstructed slices (arbitrage-free by construction):")
for name, params in rebuilt.items():
    slc = build_slice(params)
    print(f"  {name}: martingale {slc.martingale_check():.10f}, "
          f"A_R {endpoint_scales(params)[1]:.4f} < 1")

print(f"\n{LINE}\ndone.\n{LINE}")
