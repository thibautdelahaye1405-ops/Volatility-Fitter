"""American option pricing and de-Americanization (ROADMAP Phase 2 [REQ]).

Single-name listed options (AAPL, ...) are American: feeding their quotes to
a European fitter biases the smile wherever early exercise carries value
(puts under positive rates, calls around dividends). The standard desk fix
is *de-Americanization*: imply the volatility from the American price under
a binomial model, and hand the fitter that volatility as the European-
equivalent IV. Because the binomial American price is monotone in sigma,
this is a one-dimensional root-find; and since the same sigma prices the
European leg of the same tree, the classic control-variate adjustment
(market - Am(sigma*) + BS(sigma*)) collapses to BS(sigma*) exactly — i.e.
the implied sigma* IS the de-Americanized vol.

Model: Cox-Ross-Rubinstein binomial tree with continuous dividend yield q.
Discrete dividends are the dividends-model work package (data layer); until
then a yield approximation is the documented compromise. The backward
induction is vectorized over tree nodes; only the time loop is Python, so a
500-step tree prices in ~1 ms.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

#: Default tree depth: European leg matches Black-Scholes to ~1e-5 in price
#: (relative to spot), far below quote noise.
DEFAULT_STEPS = 501

#: Implied-vol search bracket (annualized).
SIGMA_LO = 1e-4
SIGMA_HI = 4.0


def binomial_price(
    is_call: bool,
    s: float,
    k: float,
    t: float,
    sigma: float,
    r: float = 0.0,
    q: float = 0.0,
    n_steps: int = DEFAULT_STEPS,
    american: bool = True,
) -> float:
    """CRR binomial price of a vanilla option (American by default).

    ``s`` spot, ``k`` strike, ``t`` year fraction, ``r``/``q`` continuously
    compounded rate and dividend yield. The CRR no-arbitrage condition
    d < e^{(r-q)dt} < u must hold; with the default depth it only fails for
    extreme drift/vol combinations, which raise rather than mis-price.
    """
    if t <= 0.0:
        intrinsic = s - k if is_call else k - s
        return max(intrinsic, 0.0)
    dt = t / n_steps
    u = float(np.exp(sigma * np.sqrt(dt)))
    d = 1.0 / u
    growth = float(np.exp((r - q) * dt))
    p = (growth - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError(
            f"CRR probability out of (0,1): sigma={sigma}, r-q={r - q}, dt={dt}"
        )
    disc = float(np.exp(-r * dt))
    pu, pd = disc * p, disc * (1.0 - p)

    # Terminal spots s * u^j * d^(n-j) = s * exp((2j - n) sigma sqrt(dt)).
    j = np.arange(n_steps + 1)
    spots = s * np.exp((2.0 * j - n_steps) * sigma * np.sqrt(dt))
    values = np.maximum(spots - k, 0.0) if is_call else np.maximum(k - spots, 0.0)

    for n in range(n_steps - 1, -1, -1):
        values = pu * values[1 : n + 2] + pd * values[: n + 1]
        if american:
            spots = s * np.exp((2.0 * np.arange(n + 1) - n) * sigma * np.sqrt(dt))
            intrinsic = spots - k if is_call else k - spots
            np.maximum(values, intrinsic, out=values)
    return float(values[0])


def deamericanize(
    is_call: bool,
    price: float,
    s: float,
    k: float,
    t: float,
    r: float = 0.0,
    q: float = 0.0,
    n_steps: int = DEFAULT_STEPS,
) -> float:
    """European-equivalent implied vol of an American option price.

    Returns the sigma* with binomial-American(sigma*) = price; by the
    control-variate identity in the module docstring this is exactly the
    de-Americanized Black vol. Returns nan when the price violates static
    bounds (below intrinsic — American prices can never be — or above s/k),
    mirroring core.black's nan convention for unusable quotes.
    """
    intrinsic = max(s - k, 0.0) if is_call else max(k - s, 0.0)
    upper = s if is_call else k  # static upper bounds (undiscounted-safe)
    if not intrinsic < price < upper:
        return float("nan")

    def objective(sigma: float) -> float:
        return binomial_price(is_call, s, k, t, sigma, r, q, n_steps) - price

    # CRR needs d < e^{(r-q)dt} < u, i.e. sigma sqrt(dt) > |r-q| dt: lift the
    # lower bracket just above that drift floor (with 50% margin).
    lo = max(SIGMA_LO, 1.5 * abs(r - q) * np.sqrt(t / n_steps))
    hi = max(0.5, 2.0 * lo)
    f_lo = objective(lo)
    if f_lo > 0.0:  # price below the near-zero-vol model price (deep ITM put
        return float("nan")  # at its early-exercise floor): no vol matches.
    while objective(hi) < 0.0:
        hi *= 2.0
        if hi > SIGMA_HI:
            return float("nan")
    return float(brentq(objective, lo, hi, xtol=1e-8, rtol=1e-10, maxiter=100))
