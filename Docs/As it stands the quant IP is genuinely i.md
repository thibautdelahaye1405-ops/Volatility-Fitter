As it stands the quant IP is genuinely interesting, especially the transported-prior + graph-propagation stack. But as a commercial competitor to Vola Dynamics, the missing pieces are less “another smile model” and more production scale, institutional workflow, validation, and adjacent risk/pricing tooling.

Vola’s public bar is high: they market whole-US-universe fitting on one box, Bayesian-style information transfer across strikes/expiries/time, arbitrage-free wings, bid/ask-derived error bars, 0DTE robustness, and stress-history credibility in [Vola Fitter](https://voladynamics.com/products/vola-fitter). Around that, they also sell flexible event/W-shaped curves via [Vola Curves](https://voladynamics.com/products/vola-curves), fast American/European pricing and Greeks via [Vola Pricer](https://voladynamics.com/products/vola-pricer), explainable portfolio PnL via [Vola PnL](https://voladynamics.com/products/vola-pnl), and event variance extraction via [Event Var Fitter](https://voladynamics.com/products/vola-event-var-fitter).

**Backend Gaps**

The biggest backend gap is scale proof. The code has a serious graph path already, but the core graph solver still has dense-matrix assumptions noted in [prior.py](C:/Users/thiba/Vol-Fitter/backend/volfit/graph/prior.py:12). That is fine for research universes; it is not yet the “whole US universe in production” story. A commercial version needs sparse Laplacian solves, selected inverse or diagonal posterior approximations, batched graph inference, and explicit latency budgets.

The calibration job model is also still workstation-shaped. [workflow.py](C:/Users/thiba/Vol-Fitter/backend/volfit/api/workflow.py:239) has a useful background calibration flow, but the commercial version needs robust scheduling: parallel lit-node calibration, resumable jobs, cancellation inside long local-vol fits, queue priorities, progress estimates, warm caches, and failure isolation per ticker/expiry.

Local vol is impressive but not yet product-safe at scale. The notes show real wins from Numba, warm starts, source-PDE variance swaps, and early stopping; the code reflects that in [affine_fit.py](C:/Users/thiba/Vol-Fitter/backend/volfit/api/affine_fit.py:938). Still missing: adaptive/non-tensor grids, hard performance tiers, fallback modes, and clear “fast enough for daily book risk” versus “research-grade exact fit” modes.

Data productionization is another major gap. To compete commercially, the app needs first-class handling for OPRA-scale history, provider reconciliation, corporate actions, borrow/rates/dividends, holidays, bad-tick quarantine, stale quote detection, entitlement boundaries, and reproducible snapshot manifests. Right now the architecture has good ingredients, but not yet the enterprise data-quality wrapper.

The platform also needs adjacent modules: full pricing API, Greeks including smart spot-vol Greeks, portfolio scenario/PnL explain, exportable surfaces, SDK/Excel integration, and model governance. Without those, it is a strong fitter; Vola is selling a fuller volatility infrastructure platform.

**Frontend UX Gaps**

The frontend has breadth, but it still feels closer to an expert lab than a sellable trader workstation. The missing top-level workflow is: load universe, fetch data, calibrate, inspect exceptions, approve surfaces, publish/export, and produce a quality report. That should be the first commercial screen.

The Graph workspace should become the product’s signature experience. Today the backend supports real provenance, transported priors, per-edge beta, quote comparison, and dark-node reconstruction in [graph_extrapolation.py](C:/Users/thiba/Vol-Fitter/backend/volfit/api/graph_extrapolation.py:1), but the UX should make it obvious: “this dark smile moved because SPY 1M moved +x bp, sector ETF edge beta was y, prior confidence was z, posterior band is ±w.”

We also need a quality dashboard: fit RMS, bid/ask hit rate, calendar/static arb status, stale nodes, filter gains, prior activation, graph skill, z-scores, and publication readiness. This is the screen that turns clever math into trust.

Commercial polish gaps include saved workspaces, keyboard navigation, virtualized large tables, persistent layouts, export/report buttons, comparison/diff views, annotations, undo for graph edits, onboarding datasets, and frontend tests. The current React app uses very few ecosystem supports, which keeps it lean, but a commercial UI needs testing, accessibility checks, and a design system.

**Improving The Unique Features**

Graph propagation should be sharpened as the central moat: “cross-asset volatility signal routing with uncertainty.” Vola publicly emphasizes transfer across strikes, expiries, and time; your differentiator can be transfer across instruments and sparse lit/dark universes.

The next leap is learned graph structure. Use historical handle innovations to estimate edge beta/confidence by regime: index-to-ETF, ETF-to-single-name, sector peers, ADR/local pairs, futures-to-index, earnings clusters. Let users start from templates, then show learned edge diagnostics.

The second leap is graph-coupled filtering. Note 15’s Kalman filter and Note 14’s graph posterior are currently adjacent ideas. The commercial-grade version should filter handle states through time and propagate innovations across the graph, with conservative covariance controls and clear explainability.

The third leap is active learning: “which dark node should I light up to reduce the most uncertainty?” That would turn graph propagation from passive extrapolation into an acquisition and calibration assistant.

The fourth is validation-as-product. Ship benchmark packs comparing graph posterior against transported prior, nearest-expiry, sector average, no-graph Kalman, and flat baselines across 25/100/500-asset captures, 0DTE, earnings, crisis-like regimes, and thin markets. The notes already contain the start of this story; it needs to become a repeatable sales artifact.

**Suggested Roadmap**

1. Commercial MVP: quality dashboard, graph explainability panel, export/publish workflow, sparse graph solver, parallel calibration queue, 25-asset historical benchmark pack.

2. Institutional MVP: auth/licensing/audit logs, provider reconciliation, snapshot reproducibility, pricing/Greeks API, Excel/Python export, portfolio scenario screen.

3. Differentiation push: learned graph edges, graph-Kalman state model, active learning, graph-to-local-vol/SLV pipeline, and benchmark reports that make the sparse dark-universe advantage undeniable.

The hard quant foundation is stronger than the product wrapper. To become a viable commercial proposal, we should make the app faster, more explainable, more validated, and easier to operate daily. The graph propagation idea is worth making the front door, not a side panel.