The calibration is very good for most names and expiries, except very short maturities. Typically 1 week expiry on SPY will fit very badly (the parametric fit is not great but very acceptable, the LV calibration is just very bad). 
I have tried to dDiagnose thoroughly the problem, and attempt to propose a fix and the associated implementation roadmap

I reviewed the Markdown/docs, especially [localvol_calibration_methodology.md](<C:/Users/thiba/Vol-Fitter/Docs/localvol_calibration_methodology.md>), [ROADMAP.md](<C:/Users/thiba/Vol-Fitter/ROADMAP.md>), prior persistence notes, graph extrapolation notes, de-Americanization notes, and the backtest findings.

**Diagnosis**

I thuink the bad 1-week SPY Local-Vol fit is most likely a structural short-end LV issue, not a bad parametric fit or de-Americanization issue.

The main likely causes are :

1. **The LV strike grid is global and long-expiry-scaled.**  
   `_delta_strike_nodes` builds one tensor strike axis using the longest-expiry scale, then clips to all observed strikes: [affine_fit.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/api/affine_fit.py:306>). For a 1-week smile, the relevant strike region is much narrower and sharper. With the default `gridXNodes=12`, the first expiry can be under-resolved even though the parametric per-slice fit is acceptable.

2. **Short-end regularization is too maturity-agnostic.**  
   The time grid adds `T1/4` before the first expiry: [affine_fit.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/api/affine_fit.py:263>). But the roughness and front-tie penalties are applied with near index-like strength, not scaled enough by the fact that `T1` is tiny: [affine_calib.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/models/localvol/affine_calib.py:548>) and [affine_calib.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/models/localvol/affine_calib.py:569>). So the first slice is asked to match sharp short-dated market curvature while also staying smooth, flat-ish, and tied to the initial row.

3. **Hybrid prior persistence can silently dominate the front expiry.**  
   New installs default to `priorPersistenceMode="hybrid"` with operator strength 50% and tail anchor 20%: [schemas.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/api/schemas.py:184>). LV consumes these as synthetic option rows, baskets, and prior varswaps: [affine_fit.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/api/affine_fit.py:751>). Unlike the parametric path, LV does not implement the data-only prepass available in [service.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/api/service.py:502>). That violates the design intent that priors should not damp live signal.

4. **There is a concrete early-stop accounting bug/design flaw.**  
   LV appends `prior_opts` into `options`: [affine_fit.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/api/affine_fit.py:821>). Then early-stop defines the “option block” as `len(options)`: [affine_calib.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/models/localvol/affine_calib.py:736>). That means synthetic prior option rows are treated like live market quotes for early stopping. On a short SPY expiry, the solver can preserve the prior/tail anchors while materially worsening live market fit.

5. **Vega-floor weighting can further loosen short wings.**  
   `_option_quotes` floors vega at `1e-3`: [affine_fit.py](<C:/Users/thiba/Vol-Fitter/backend/volfit/api/affine_fit.py:481>). For 1-week OTM quotes, many vegas are tiny. This can make wing residuals less like true implied-vol residuals, so LV may ignore precisely the part of the short smile that visually looks worst.

**Robust Fix**

I would fix this in layers, with the first two being highest confidence.

1. **Separate live market rows from prior rows in LV.**  
   Keep `market_options`, `prior_options`, `market_varswaps`, and `prior_varswaps` distinct. Early-stop, per-expiry RMS, and headline fit diagnostics should use live market rows only. Prior rows should remain penalties, never be counted as market fit quality.

2. **Implement LV data-only prepass for prior persistence.**  
   Mirror the parametric `priorDataOnlyPrepass` behavior for LV. First solve market-only LV, then add only genuinely under-observed prior operators. Initialize the final solve from the data-only theta. For very short expiries, require stronger evidence before enabling RR/BF/VarSwap/tail priors.

3. **Make short-expiry priors maturity-aware.**  
   For `T < 14d` or configurable threshold, either disable prior varswap/tail anchors by default or cap their effective weight. Do not let prior varswap alone force `fit_left_a=True`, because that changes the solver path and can disable the intended GN route.

4. **Add short-end strike micro-nodes.**  
   Replace the single longest-expiry-scaled x-axis with a union of per-expiry delta nodes, especially for the first few expiries. Keep the tensor grid, but augment it with nodes based on `sigma(T_i) * sqrt(T_i)` so the 1-week smile has enough local degrees of freedom.

5. **Scale regularization by physical maturity.**  
   Rework time roughness and front-tie weights so tiny front intervals are not penalized like ordinary index steps. At minimum, weaken `frontTieWeight` and time roughness when `T1` is very short. Better: discretize a continuous-time roughness integral using actual interval lengths.

6. **Improve short-wing weighting diagnostics.**  
   Report how many quotes hit `_VEGA_FLOOR` by expiry. If SPY 1-week wings are mostly floor-weighted, use a lower relative floor or an implied-vol-space residual for short maturities.

**Implementation Roadmap**

Phase 1: Add diagnostics only. Per expiry, report live RMS, prior-option RMS, basket RMS, varswap RMS, roughness contribution, front-tie contribution, active bounds, and vega-floor count.

Phase 2: Fix the early-stop/block accounting. This is the most direct code-level issue and should be regression-tested with hybrid prior on/off.

Phase 3: Add LV data-only prepass and maturity-aware prior gating. Acceptance criterion: prior-enabled LV should not worsen live 1-week SPY RMS versus prior-off by more than a small tolerance.

Phase 4: Add short-expiry strike micro-grid. Acceptance criterion: 1-week SPY LV RMS should move close to the parametric fit without degrading normal SPY/NVDA/NDX surfaces.

Phase 5: Rework front regularization scaling. Acceptance criterion: better 1-week fits with stable local variance, no new arbitrage failures, and no material perf regression.

My strongest bet: the SPY 1-week failure is a combination of under-resolved short strike geometry plus prior/early-stop leakage. The early-stop/prior separation is the first fix I would make, because it is clearly wrong even before we tune the numerical model.