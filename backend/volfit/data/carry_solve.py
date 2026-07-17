"""Joint borrow / de-Americanization fixed point (R2 item 11, increment 1).

CarryCurve v0 reads borrow as ``ln(F_theo / F_parity) / t`` with BOTH legs
computed off raw American mids — on a hard-to-borrow name that read is
EEP-contaminated twice: the parity regression runs on American prices whose
early-exercise premium depends on the very borrow being measured, and the
de-Americanization inside ``implied_forward`` uses a LUMPED implied carry
(q absorbs dividends + borrow together), which mistimes exercise around
discrete ex-dates.

The fixed point closes the loop with the carry SPLIT and the SAME dividend
schedule in both legs (the item's "discrete dividends consistent" clause):

    b_0 = 0
    repeat:
      1. de-Americanize the chain's paired mids on the tree at
         (rate, q = b_i, escrowed cash schedule)  ->  European sigmas;
      2. reprice those sigmas EUROPEAN on the same tree/carry and regress
         parity  C - P = D (F - K)                ->  F_parity(b_i);
      3. F_theo(b_i) = (S - PV(divs)) * exp((rate - b_i) t);
         gap g = ln(F_theo(b_i) / F_parity) / t;  b_{i+1} = b_i + g
    until |g| < tol.

(Sign: a hard-to-borrow name trades its parity forward BELOW theoretical,
so a positive gap raises b — exactly solving F_theo(b_new) = F_parity when
F_parity is insensitive to b.) At the true borrow the de-Americanized call
and put sigmas agree, parity holds at the theoretical forward, and the gap
vanishes; the update is exact in b up to the (weak) EEP-dependence of
F_parity on b, so it contracts in 2-4 iterations.
Increment 1 is MEASUREMENT-GRADE: it upgrades the carry view (borrow,
iterations, tree-failure counts — the exit gate's explicit failure rates)
and feeds no fit; routing the converged (F, D) into prepared quotes is the
gated increment 2. Ordinary names: with no dividends and b ~ 0 the loop
converges immediately to the v0 read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from volfit.core.american import binomial_price_batch, deamericanize_batch
from volfit.data.types import ChainSnapshot

#: Convergence tolerance on the borrow update (continuous, per year): 1e-5 =
#: 0.1 bp — far below the identifiability noise of any real parity read.
TOL = 1e-5
MAX_ITER = 8
#: Physical bound on |borrow|: past 200%/yr the read is data garbage, not a
#: financing rate — the solve reports non-convergence instead of chasing it.
BORROW_CAP = 2.0
#: Tree resolution for the solve: the gap signal is a LEVEL read (like the
#: forward de-bias), so the coarse fast settings suffice.
N_STEPS = 96
BISECTIONS = 20
#: Minimum same-strike call/put pairs for the regression to mean anything
#: (mirrors carry.CARRY_MIN_STRIKES).
MIN_PAIRS = 6


def iv_borrow_sensitivity_bp(t: float, atm_vol: float | None = None) -> float | None:
    """ATM implied vol moved (bp) by 100 bp of borrow, at FIXED strike and
    price (R2 item 11 increment 3 — "IV-sensitivity to borrow uncertainty").

    Closed form: the forward responds dF = -t F db, and re-inverting an
    unchanged ATM price gives dsigma/dF = -(dC/dF)/vega, so

        dsigma/db = t F (D N(d1)) / (D F phi(d1) sqrt(t)) = sqrt(t) N(d1)/phi(d1)

    with d1 = sigma sqrt(t)/2 at the money. Per 100 bp of borrow that is
    ``100 sqrt(t) N(d1)/phi(d1)`` vol bp — ~125 sqrt(t) at low sigma*sqrt(t),
    growing mildly with it. ``atm_vol=None`` uses the sigma->0 limit (d1=0):
    the factor is weakly sigma-dependent, so the fit-free read stays honest.
    This is the trader's materiality number: an UNIDENTIFIED borrow matters
    exactly when this sensitivity times the plausible borrow range is large
    (the strategic publish rule's "material x unidentified" product).

    De-Am carry response is deliberately excluded (second order for the
    diagnostic; the joint solve owns the exact treatment). None when t <= 0.
    """
    from volfit.core.black import norm_cdf, norm_pdf

    if t <= 0.0:
        return None
    d1 = 0.5 * float(atm_vol or 0.0) * np.sqrt(t)
    return float(100.0 * np.sqrt(t) * norm_cdf(d1) / norm_pdf(d1))


def dividend_legs(settings, reference_date: date):
    """(dividend_yield, div_times, div_amounts) from a MarketSettings-shaped
    object, or None when the model mix is unsupported (a PROPORTIONAL
    dividend is not a cash amount the escrowed tree can carry — callers fall
    back to the v0 read). Shared by the carry view and the fit-path gate so
    both legs always see the same schedule."""
    if settings.dividendMode == "discrete_proportional":
        return None
    div_times = div_amounts = None
    if settings.dividendMode in ("discrete_absolute", "mixed"):
        legs = [
            ((date.fromisoformat(d.exDate) - reference_date).days / 365.0, d.amount)
            for d in settings.dividends
        ]
        legs = [(tt, a) for tt, a in legs if tt > 0.0]
        if legs:
            div_times = np.array([tt for tt, _ in legs])
            div_amounts = np.array([a for _, a in legs])
    return float(settings.dividendYield), div_times, div_amounts


@dataclass(frozen=True)
class JointBorrowResult:
    """The converged joint read for one expiry, failure accounting included."""

    borrow_bp: float  # continuous borrow, bp/yr (positive = hard-to-borrow)
    forward: float  # parity forward at the converged carry
    discount: float
    iterations: int
    converged: bool
    n_pairs: int  # same-strike C/P pairs behind the regression
    deam_failures: int  # quotes the tree could not invert at the final carry


def _paired_mids(snapshot: ChainSnapshot, expiry: date):
    """Same-strike (K, call mid, put mid) arrays — the parity information set."""
    call: dict[float, float] = {}
    put: dict[float, float] = {}
    for q in snapshot.quotes_for(expiry):
        if q.mid is None:
            continue
        (call if q.call_put == "C" else put)[q.strike] = q.mid
    strikes = sorted(set(call) & set(put))
    return (
        np.array(strikes, dtype=float),
        np.array([call[s] for s in strikes]),
        np.array([put[s] for s in strikes]),
    )


def _parity_fit(strikes: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """(forward, discount) from the plain parity regression y = a - D*K."""
    a, b = np.linalg.lstsq(
        np.column_stack([np.ones_like(strikes), strikes]), y, rcond=None
    )[0]
    discount = -float(b)
    return (float(a) / discount if discount > 0.0 else float("nan")), discount


def joint_borrow(
    snapshot: ChainSnapshot,
    expiry: date,
    reference_date: date,
    rate: float,
    dividend_yield: float = 0.0,
    div_times: np.ndarray | None = None,
    div_amounts: np.ndarray | None = None,
    max_iter: int = MAX_ITER,
    tol: float = TOL,
) -> JointBorrowResult | None:
    """The fixed point for one expiry, or None when the data cannot carry it
    (no time to expiry, too few pairs, zero-carry synthesized chain).

    ``dividend_yield`` is the continuous leg of the dividend model; it rides
    the tree as part of q (q = yield + borrow) and the theoretical forward
    symmetrically, so both legs stay consistent whatever the model mix."""
    t = (expiry - reference_date).days / 365.0
    if t <= 0.0 or snapshot.is_zero_carry():
        return None
    strikes, c_mid, p_mid = _paired_mids(snapshot, expiry)
    if strikes.size < MIN_PAIRS:
        return None
    s = float(snapshot.spot)
    pv_divs = 0.0
    if div_times is not None and div_amounts is not None and len(div_times):
        tt = np.asarray(div_times, dtype=float)
        aa = np.asarray(div_amounts, dtype=float)
        live = (tt > 0.0) & (tt < t)
        pv_divs = float(np.sum(aa[live] * np.exp(-rate * tt[live])))
    if s - pv_divs <= 0.0:
        return None

    is_call = np.concatenate([np.ones(strikes.size, bool), np.zeros(strikes.size, bool)])
    k_all = np.concatenate([strikes, strikes])
    mids = np.concatenate([c_mid, p_mid])

    if snapshot.exercise_style != "american":
        # European: no early-exercise premium, so parity on the RAW mids is
        # already clean and the fixed point collapses to a single exact step
        # (F_parity does not depend on b; b just closes the theo-forward gap).
        forward, discount = _parity_fit(strikes, c_mid - p_mid)
        if not np.isfinite(forward) or forward <= 0.0 or discount <= 0.0:
            return None
        f_theo0 = (s - pv_divs) * float(np.exp((rate - dividend_yield) * t))
        return JointBorrowResult(
            borrow_bp=float(np.log(f_theo0 / forward) / t * 1e4),
            forward=float(forward), discount=float(discount),
            iterations=1, converged=True, n_pairs=int(strikes.size),
            deam_failures=0,
        )

    b = 0.0
    forward = discount = float("nan")
    failures = 0
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):
        # De-Americanize on the SPLIT carry (rate, yield + borrow, cash schedule).
        sigma = deamericanize_batch(
            is_call, mids, s, k_all, t, r=rate, q=dividend_yield + b,
            n_steps=N_STEPS, bisections=BISECTIONS,
            div_times=div_times, div_amounts=div_amounts,
        )
        good = np.isfinite(sigma)
        failures = int(np.sum(~good))
        pair_ok = good[: strikes.size] & good[strikes.size:]
        if int(np.sum(pair_ok)) < MIN_PAIRS:
            break  # the tree cannot support a regression at this carry
        eur = binomial_price_batch(
            is_call, s, k_all, t, np.where(good, sigma, 0.2),
            r=rate, q=dividend_yield + b,
            n_steps=N_STEPS, american=False,
            div_times=div_times, div_amounts=div_amounts,
        )
        y = eur[: strikes.size][pair_ok] - eur[strikes.size:][pair_ok]
        forward, discount = _parity_fit(strikes[pair_ok], y)
        f_theo = (s - pv_divs) * float(np.exp((rate - dividend_yield - b) * t))
        if not np.isfinite(forward) or forward <= 0.0 or f_theo <= 0.0:
            break
        gap = float(np.log(f_theo / forward)) / t
        b += gap
        if abs(b) > BORROW_CAP:
            break  # data garbage, not a financing rate
        if abs(gap) < tol:
            converged = True
            break

    if not np.isfinite(forward) or forward <= 0.0:
        return None
    return JointBorrowResult(
        borrow_bp=float(b * 1e4),
        forward=float(forward),
        discount=float(discount),
        iterations=iterations,
        converged=converged,
        n_pairs=int(strikes.size),
        deam_failures=failures,
    )
