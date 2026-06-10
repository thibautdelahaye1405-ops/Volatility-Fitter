Volatility Fitter

The goal is to create a impplied volatility fitter, like https://voladynamics.com/products/vola-fitter but with an additional feature : extrapolate sparse observations to the full universe of smiles, across expiries and assets. The idea for this extrapolation is to propoagate the signal through a graph, which nodes are smile (underlying, T). 


******************

Several components : 

1) Data layer
- options prices / IV : Yahoo Finance scraping, Bloomberg API, Massive
- To be determined for dividends
- Universe selection : user picks among all possible asset tickers and expiries available

2) Hyper parameters
- Vol surface models : SVI-JW, LQD (see document in \Docs), Sigmoid, Full Local Volatility grid (continuous and piecewise affine across a strike x T grid)
- Optimization parameters (penalties coefficients)
- Activation toggle for calendar arbitrage prevention
- Activation toggle for event dilation of time
- Vol-Spot dynamics : SSR on ATM-vol, sticky-strike, sticky local-vol grid
- Graph solver and related parameters

3) Smile viewer
- chart prior / current fit vs quote bands, in normalized or fixed strike
- chart quantile fu ction and LQD prior / current
- save prior
- chart Term-STructure and event-dilated calendar, in vol and in variance
- slide-bars for strike range, zoom capabilities
- select / erase / amend quote points for calibration
- var-swap level
- fit to bid-ask or fit to mid or fit to haircut bid-ask

4) Graph viewer
- Weights inoput
- Nodes selection lit / dark
- Visualization
- Solver (see note in \Docs)

**********************

Tech stack :
Python backend
React Front-End (or anything better ?)
SQL Lite for data (or anything more suitable ?)

**********************

Policies :
Avoid files exceeding 400 lines
Comment codebase clearly and cleanly, so it can be read by human or other agents
Compute time should be optimized ; calculations should be lightning-fast
UX should be professional, commercial, super sleek
Lead and Spawn multiple sub-specialized sub-agents
