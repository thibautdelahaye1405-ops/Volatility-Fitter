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

Batch variants ([REQ 2026-06-12] realism block): the scalar Brent inversion
costs ~1 ms of tree evals per iteration, fine for one option but seconds
for a whole chain — too slow for quote prep under the lightning-fast
policy. `binomial_price_batch` prices every quote of a chain per tree
sweep ((n, m) slabs, one Python loop over time only), and
`deamericanize_batch` bisects all quotes simultaneously, so the entire
chain inverts in a few dozen sweeps total.
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

#: Tree depth for *batched* quote prep: European leg within a few 1e-4 of
#: Black in price — below quote noise — while a full chain prices in tens of
#: milliseconds. The scalar default stays at the deeper DEFAULT_STEPS.
DEFAULT_BATCH_STEPS = 192

#: Bisection sweeps in deamericanize_batch: halving a <= SIGMA_HI bracket 45
#: times leaves < 2e-13 of sigma uncertainty, comparable to the scalar
#: Brent tolerances.
BATCH_BISECTIONS = 45


def _escrow(
    s: float,
    r: float,
    t: float,
    n_steps: int,
    div_times: np.ndarray | None,
    div_amounts: np.ndarray | None,
) -> tuple[float, np.ndarray]:
    """Escrowed-cash-dividend lattice base and per-step PV add-back (Hull).

    For discrete cash dividends D_i at ex-times tau_i in (0, t], the
    recombining CRR runs on the dividend-stripped base S - PV_0 (PV of all
    dividends to expiry), and the ACTUAL stock at step n is
    base_lattice + pv_step[n], where pv_step[n] discounts back only the
    dividends still in the future at t_n = n dt. This keeps the tree
    recombining (fast) while pricing early exercise off the true spot.
    Returns (base, pv_step) with pv_step length n_steps+1; pv_step[n_steps]=0
    (no dividend lies beyond expiry), so the terminal payoff uses the base
    lattice directly.
    """
    if div_times is None or len(div_times) == 0:
        return s, np.zeros(n_steps + 1)
    dts = np.asarray(div_times, dtype=float)
    damt = np.asarray(div_amounts, dtype=float)
    t_grid = np.linspace(0.0, t, n_steps + 1)
    future = dts[None, :] > t_grid[:, None]  # dividends still ahead at each step
    pv = np.where(future, damt[None, :] * np.exp(-r * (dts[None, :] - t_grid[:, None])), 0.0)
    pv_step = pv.sum(axis=1)
    return float(s - pv_step[0]), pv_step


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
    div_times: np.ndarray | None = None,
    div_amounts: np.ndarray | None = None,
) -> float:
    """CRR binomial price of a vanilla option (American by default).

    ``s`` spot, ``k`` strike, ``t`` year fraction, ``r``/``q`` continuously
    compounded rate and dividend yield. The CRR no-arbitrage condition
    d < e^{(r-q)dt} < u must hold; with the default depth it only fails for
    extreme drift/vol combinations, which raise rather than mis-price.

    ``div_times``/``div_amounts`` add a discrete CASH dividend schedule (ex
    year-fractions in (0, t] and cash amounts), priced by the escrowed-spot
    method (``_escrow``); pass ``q=0`` with them. Continuous ``q`` and discrete
    cash can also coexist (a continuous proxy for far-dated proportional yield).
    """
    if t <= 0.0:
        intrinsic = s - k if is_call else k - s
        return max(intrinsic, 0.0)
    dt = t / n_steps
    sqdt = float(np.sqrt(dt))
    base, pv_step = _escrow(s, r, t, n_steps, div_times, div_amounts)
    if base <= 0.0:
        return float("nan")  # dividend PV swallows the spot: no usable lattice
    u = float(np.exp(sigma * sqdt))
    d = 1.0 / u
    growth = float(np.exp((r - q) * dt))
    p = (growth - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError(
            f"CRR probability out of (0,1): sigma={sigma}, r-q={r - q}, dt={dt}"
        )
    disc = float(np.exp(-r * dt))
    pu, pd = disc * p, disc * (1.0 - p)

    # Terminal ACTUAL spots: base lattice (+ pv_step[N] = 0 at expiry).
    j = np.arange(n_steps + 1)
    actual = base * np.exp((2.0 * j - n_steps) * sigma * sqdt) + pv_step[n_steps]
    values = np.maximum(actual - k, 0.0) if is_call else np.maximum(k - actual, 0.0)

    for n in range(n_steps - 1, -1, -1):
        values = pu * values[1 : n + 2] + pd * values[: n + 1]
        if american:
            actual = base * np.exp((2.0 * np.arange(n + 1) - n) * sigma * sqdt) + pv_step[n]
            intrinsic = actual - k if is_call else k - actual
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
    div_times: np.ndarray | None = None,
    div_amounts: np.ndarray | None = None,
) -> float:
    """European-equivalent implied vol of an American option price.

    Returns the sigma* with binomial-American(sigma*) = price; by the
    control-variate identity in the module docstring this is exactly the
    de-Americanized Black vol. Returns nan when the price violates static
    bounds (below intrinsic — American prices can never be — or above s/k),
    mirroring core.black's nan convention for unusable quotes.
    ``div_times``/``div_amounts`` apply the escrowed cash dividend schedule.
    """
    intrinsic = max(s - k, 0.0) if is_call else max(k - s, 0.0)
    upper = s if is_call else k  # static upper bounds (undiscounted-safe)
    if not intrinsic < price < upper:
        return float("nan")

    def objective(sigma: float) -> float:
        return (
            binomial_price(is_call, s, k, t, sigma, r, q, n_steps, True, div_times, div_amounts)
            - price
        )

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


def binomial_price_batch(
    is_call: np.ndarray,
    s: float,
    k: np.ndarray,
    t: float,
    sigma: np.ndarray,
    r: float = 0.0,
    q: float = 0.0,
    n_steps: int = DEFAULT_BATCH_STEPS,
    american: bool = True,
    div_times: np.ndarray | None = None,
    div_amounts: np.ndarray | None = None,
) -> np.ndarray:
    """CRR prices of n quotes at once (per-quote lattice, vectorized across quotes).

    ``is_call``/``k``/``sigma`` are same-length arrays; the arithmetic per
    quote is identical to `binomial_price` at equal ``n_steps`` (same
    expression grouping, so the two agree to machine precision). Quotes
    whose CRR probability falls outside (0, 1) — nan sigma, or near-zero
    sigma against a large drift — come back nan instead of raising: a batch
    must survive mixed inputs (this deliberately differs from the scalar).
    ``div_times``/``div_amounts`` add the same escrowed CASH dividend schedule
    as the scalar (shared across all quotes, since spot/rate/dividends are).
    """
    is_call = np.asarray(is_call, dtype=bool)
    k = np.asarray(k, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    if t <= 0.0:
        return np.maximum(np.where(is_call, s - k, k - s), 0.0)

    dt = t / n_steps
    sqrt_dt = float(np.sqrt(dt))
    base, pv_step = _escrow(s, r, t, n_steps, div_times, div_amounts)
    if base <= 0.0:
        return np.full(k.shape, np.nan)
    u = np.exp(sigma * sqrt_dt)
    d = 1.0 / u
    growth = float(np.exp((r - q) * dt))
    with np.errstate(invalid="ignore", divide="ignore"):
        p = (growth - d) / (u - d)
    bad = ~((p > 0.0) & (p < 1.0))  # nan-safe: nan fails both comparisons
    disc = float(np.exp(-r * dt))
    pu = (disc * p)[:, None]
    pd = (disc * (1.0 - p))[:, None]
    kk = k[:, None]
    call_col = is_call[:, None]
    sig_col = sigma[:, None]

    def actual_slab(m: int) -> np.ndarray:
        """(n, m+1) ACTUAL spot lattice at step m: base CRR lattice on
        s - PV_0 plus the escrowed dividend PV still ahead at t_m."""
        j = np.arange(m + 1)
        return base * np.exp((2.0 * j - m) * sig_col * sqrt_dt) + pv_step[m]

    # Bad lanes (nan/extreme sigma) still flow through the induction and are
    # masked to nan at the end — silence their overflow/invalid noise.
    with np.errstate(over="ignore", invalid="ignore"):
        spots = actual_slab(n_steps)
        values = np.maximum(np.where(call_col, spots - kk, kk - spots), 0.0)
        for m in range(n_steps - 1, -1, -1):
            values = pu * values[:, 1 : m + 2] + pd * values[:, : m + 1]
            if american:
                spots = actual_slab(m)
                intrinsic = np.where(call_col, spots - kk, kk - spots)
                np.maximum(values, intrinsic, out=values)
    out = values[:, 0].copy()
    out[bad] = np.nan
    return out


def deamericanize_batch(
    is_call: np.ndarray,
    prices: np.ndarray,
    s: float,
    k: np.ndarray,
    t: float,
    r: float = 0.0,
    q: float = 0.0,
    n_steps: int = DEFAULT_BATCH_STEPS,
    bisections: int = BATCH_BISECTIONS,
    div_times: np.ndarray | None = None,
    div_amounts: np.ndarray | None = None,
) -> np.ndarray:
    """De-Americanize a whole chain at once via vectorized bisection.

    Same contract per quote as the scalar `deamericanize` (nan for unusable
    prices), but every iteration evaluates one `binomial_price_batch` over
    all still-active quotes, so a few dozen tree sweeps invert hundreds of
    quotes. Screens mirror the scalar: static bounds first, then the CRR
    drift floor ``lo`` — quotes priced below the near-zero-vol model price
    (e.g. a deep-ITM put at its early-exercise floor) and quotes never
    bracketed by SIGMA_HI come back nan. ``bisections`` halvings of a
    <= SIGMA_HI bracket leave ~SIGMA_HI/2^bisections of sigma uncertainty
    (the default lands within ~2e-13; callers that only need a few bp of vol,
    e.g. the forward de-bias, pass a smaller count to trade precision for
    speed).
    """
    is_call = np.asarray(is_call, dtype=bool)
    prices = np.asarray(prices, dtype=float)
    k = np.asarray(k, dtype=float)
    out = np.full(prices.shape, np.nan)
    if t <= 0.0:
        return out  # expired: only intrinsic trades, no vol to imply

    # Static no-arbitrage screen (strict bounds, as in the scalar).
    intrinsic = np.maximum(np.where(is_call, s - k, k - s), 0.0)
    upper = np.where(is_call, s, k)
    idx = np.flatnonzero((prices > intrinsic) & (prices < upper))
    if idx.size == 0:
        return out
    ic, px, kk = is_call[idx], prices[idx], k[idx]

    def price_at(sig: np.ndarray) -> np.ndarray:
        return binomial_price_batch(
            ic, s, kk, t, sig, r, q, n_steps, True, div_times, div_amounts
        )

    # Lower bracket just above the CRR drift floor (same margin as scalar).
    lo = max(SIGMA_LO, 1.5 * abs(r - q) * float(np.sqrt(t / n_steps)))
    lo_arr = np.full(idx.size, lo)
    ok = price_at(lo_arr) <= px  # nan-safe: model price above target -> drop

    # Upper bracket: double until the model price clears the target. Starting
    # at >= 0.5 with the SIGMA_HI cap bounds this to a handful of sweeps.
    hi_arr = np.full(idx.size, max(0.5, 2.0 * lo))
    pending = ok.copy()
    while pending.any():
        pending &= ~(price_at(hi_arr) >= px)  # still below target (or nan)
        hi_arr[pending] *= 2.0
        over = pending & (hi_arr > SIGMA_HI)
        ok &= ~over  # never bracketed within SIGMA_HI: no vol matches
        pending &= ~over

    # Bisect the whole batch in lockstep (one tree sweep per iteration).
    for _ in range(bisections):
        mid = 0.5 * (lo_arr + hi_arr)
        go_up = price_at(mid) < px  # root above mid (nan -> False, harmless)
        lo_arr = np.where(go_up, mid, lo_arr)
        hi_arr = np.where(go_up, hi_arr, mid)

    root = 0.5 * (lo_arr + hi_arr)
    root[~ok] = np.nan
    out[idx] = root
    return out
