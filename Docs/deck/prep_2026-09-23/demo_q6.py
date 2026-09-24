"""Transport one SVI-JW slice under each regime for a +1% spot move.
Reports: ATM vol / skew / curvature (numeric handles, the app's diagnostics),
the vol at a FIXED strike (K = F0, old k=0 -> new k=-h) and at a fixed
moneyness (k=-0.10), plus the LV grid node relabel. No app state touched."""
import numpy as np
from volfit.models.svi_jw.svi import SVIJW, jw_to_raw
from volfit.models.diagnostics import numeric_handles
from volfit.dynamics.transport import TransportedSlice, transport_grid_logk, beta_of, ell_T
from volfit.dynamics.ssr import ssr_of_regime

t = 0.5
jw = SVIJW(t=t, v=0.04, psi=-0.35*np.sqrt(0.04)*2, p=0.9, c=0.4, v_tilde=0.035)  # ATM vol 20%, skew ~-0.35 in vol per unit k
# psi in SVI-JW is d sqrt(w)/dk at k=0 scaled: use jw_to_raw and read the numeric skew instead
raw = jw_to_raw(jw)
base_h = numeric_handles(raw, t)
print(f"anchor: ATM {base_h.atm_vol:.4%}  skew {base_h.skew:+.4f}  curv {base_h.curvature:+.3f}")
shift = 0.01
h = np.log1p(shift)
print(f"spot move +1% -> h = log(F1/F0) = {h:+.6f}")
print()
print(f"{'regime':22s} {'R':>4s} {'ATM vol':>9s} {'dATM(bp)':>9s} {'R*skew*h(bp)':>13s} {'skew':>8s} {'curv':>7s} {'vol@K=F0':>9s} {'vol@k=-.10':>10s} {'beta':>5s}")
for regime in ("sticky_moneyness", "sticky_strike", "sticky_local_vol", 1.5):
    R = ssr_of_regime(regime)
    moved = TransportedSlice(raw, h, regime, sigma0=base_h.atm_vol, kappa=base_h.skew, tau=t)
    hh = numeric_handles(moved, t)
    v_fixed_strike = float(moved.implied_vol(-h, t))       # old ATM strike K=F0 sits at new k=-h
    v_fixed_k = float(moved.implied_vol(-0.10, t))
    print(f"{str(regime):22s} {R:4.1f} {hh.atm_vol:9.4%} {(hh.atm_vol-base_h.atm_vol)*1e4:9.1f} {R*base_h.skew*h*1e4:13.1f} {hh.skew:+8.4f} {hh.curvature:+7.3f} {v_fixed_strike:9.4%} {v_fixed_k:10.4%} {beta_of(regime) if not isinstance(regime,float) else beta_of(regime):5.2f}")
print()
print(f"anchor vol at K=F0 (k=0): {base_h.atm_vol:.4%} ; anchor vol at k=-0.10: {float(raw.implied_vol(-0.10,t)):.4%}")
print(f"ell_T(0,h) = {float(ell_T(0.0,h)):+.6f}  (~2h = {2*h:+.6f}) ; ell_T(-0.3,h) = {float(ell_T(-0.3,h))+0.3:+.6f} displacement vs (1+e^0.3)h = {(1+np.exp(0.3))*h:+.6f}")
grid = np.array([-0.2, -0.1, 0.0, 0.1, 0.2])
for regime in ("sticky_moneyness", "sticky_strike", "sticky_local_vol"):
    print(f"LV grid x-nodes under {regime:18s}: {np.round(transport_grid_logk(grid, h, regime), 5)}  (x - R/2 h; absolute K scales by e^(beta h), beta={beta_of(regime):.1f})")
# SVI raw params: unchanged by construction (the wrapper never touches them)
print("\nraw SVI params behind the transport wrapper:", raw)
print("moved._base is raw:", moved._base is raw)
