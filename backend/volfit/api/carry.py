"""CarryCurve v0 — the per-ticker carry object with provenance (R1 item 7).

Today the carry story is spread across three layers: the parity regression
(forward + discount per expiry), the dividend model (MarketSettings), and a
flat desk rate. Borrow exists only IMPLICITLY, as the gap between the
parity-implied forward and the rate+dividend theoretical forward. This
module names that structure:

    borrow(T) = q_parity(T) - q_dividend(T) = ln(F_theo / F_parity) / T

(the flat rate cancels — the read is exactly the option market's carry in
excess of the dividend model; positive = hard-to-borrow pushes the parity
forward BELOW theoretical). Every component carries a source tag and the
borrow leg carries an explicit identifiability verdict:

  * identified  — a real parity regression stands behind the expiry (not a
    zero-carry synthesized chain, enough parity pairs, residuals in line);
  * unidentified — the CALM, COMMON state for single names: thin chains,
    zero-carry fallbacks, manual/theoretical forward modes. Reported as
    None, NEVER as a silent zero-borrow.

v0 is measurement + provenance only: nothing here feeds a fit (the joint
borrow/de-Americanization fixed point is the R2 item), and the quality
surface is advisory. Versioned by the same counters the fit caches key on.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volfit.api.schemas import CarryCurveResponse, CarryPoint
from volfit.api.state import AppState

#: Minimum parity pairs behind an expiry for its borrow read to count.
CARRY_MIN_STRIKES = 6
#: Parity residual RMS ceiling as a fraction of spot: beyond it the
#: regression is too noisy to attribute the forward gap to borrow.
CARRY_RMS_FRAC = 1e-3

_SOURCE = {"parity": "parity_implied", "manual": "desk", "theoretical": "model"}


def implied_borrow_bp(
    f_parity: float, f_theo: float, t: float
) -> float | None:
    """Continuous option-implied borrow (bp/yr) from the forward gap."""
    if t <= 0.0 or f_parity <= 0.0 or f_theo <= 0.0:
        return None
    return float(np.log(f_theo / f_parity) / t * 1e4)


def borrow_identified(
    parity, zero_carry: bool, spot: float
) -> bool:
    """Whether the expiry's parity regression can carry a borrow read."""
    return (
        parity is not None
        and not zero_carry
        and parity.n_strikes >= CARRY_MIN_STRIKES
        and parity.residual_rms <= CARRY_RMS_FRAC * spot
    )


def _point(state: AppState, ticker: str, expiry: date, zero_carry: bool, spot: float) -> CarryPoint:
    parity = state.forwards(ticker).get(expiry)
    theo_forward, _ = state.theoretical_forward_for(ticker, expiry)
    active = state.resolved_forward(ticker, expiry)
    t = state.year_fraction(expiry)
    identifiable = borrow_identified(parity, zero_carry, spot)
    borrow = (
        implied_borrow_bp(parity.forward, theo_forward, t) if identifiable else None
    )
    source = _SOURCE.get(active.source, active.source)
    return CarryPoint(
        expiry=expiry.isoformat(),
        t=t,
        forward=float(active.forward),
        forwardSource=source,
        discount=float(active.discount),
        # The discount rides the forward resolution: parity's regressed D, or
        # the desk-rate fallback under manual/theoretical modes.
        discountSource="parity_implied" if active.source == "parity" else "desk",
        borrowBp=borrow,
        borrowSource="parity_implied" if borrow is not None else "unidentified",
        identifiable=identifiable,
        nStrikes=0 if parity is None else int(parity.n_strikes),
        residualRms=0.0 if parity is None else float(parity.residual_rms),
        nOutliers=0 if parity is None else int(parity.n_outliers),
    )


def carry_curve(state: AppState, ticker: str) -> CarryCurveResponse:
    """Assemble the ticker's carry object from cached state (never fits)."""
    snapshot = state.snapshot(ticker)  # UnknownNodeError on bad tickers
    settings = state.market_settings(ticker)
    zero_carry = snapshot.is_zero_carry()
    points = [
        _point(state, ticker, expiry, zero_carry, float(snapshot.spot))
        for expiry in sorted(state.forwards(ticker))
    ]
    has_divs = bool(settings.dividends) or settings.dividendYield != 0.0
    identified = sum(1 for p in points if p.borrowBp is not None)
    return CarryCurveResponse(
        ticker=ticker,
        spot=float(snapshot.spot),
        rate=settings.rate,
        rateSource="desk",
        dividendMode=settings.dividendMode,
        dividendSource="desk" if has_divs else "none",
        zeroCarry=zero_carry,
        forwardsVersion=state.forwards_version(ticker),
        dataVersion=state.data_version(ticker),
        points=points,
        identified=identified,
        unidentified=len(points) - identified,
    )


def carry_counts(state: AppState, ticker: str) -> tuple[int, int]:
    """(identified, unidentified) borrow reads — the advisory quality rollup.

    Best-effort: a status read must never break on a carry hiccup."""
    try:
        curve = carry_curve(state, ticker)
    except Exception:  # noqa: BLE001 — advisory surface only
        return 0, 0
    return curve.identified, curve.unidentified
