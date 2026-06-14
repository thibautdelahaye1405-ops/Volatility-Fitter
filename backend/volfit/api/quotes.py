"""Chain snapshot -> slice-calibration inputs (ROADMAP Phase 5 quote prep).

For one (ticker, expiry) with resolved forward F and discount D (parity,
theoretical or manual — volfit.data.forwards.ResolvedForward; only the
`.forward`/`.discount` attributes are used, so an ImpliedForward works too),
each quoted strike K maps to log-moneyness k = ln(K / F), keeping only the
OTM side (call for K >= F, put below): the OTM option carries the vega and
the tight relative spread. Option prices p are normalized to undiscounted
forward units, puts converted to calls by parity in those units (conventions
of volfit.core.black),

    c = p / (D F)              (calls)
    c = p / (D F) + 1 - e^k    (puts),

then inverted strike by strike to total implied variance. The map is
monotone, so bid <= mid <= ask survives into implied-vol space. Strikes
whose bid, mid or ask violates the static bounds (1-e^k)^+ < c < 1 are
dropped entirely — a one-sided band cannot be displayed or weighted.

De-Americanization (ROADMAP realism block, [REQ 2026-06-12]): when the
snapshot's `exercise_style` is "american", quoted prices carry an early-
exercise premium (EEP) the European pipeline above would misread as extra
vol. Each *mid* is inverted through a CRR binomial tree
(volfit.core.american.deamericanize_batch) to its European-equivalent sigma;
repricing that sigma with Black gives the European mid, and EEP =
max(raw_mid - european_mid, 0) — clamped at zero because the premium is
theoretically nonnegative while quote noise can dip below. The SAME EEP is
subtracted from raw bid/mid/ask, preserving the quoted spread in price space
at the cost of one root-find per quote instead of three. Quotes the tree
cannot invert (nan sigma) keep their raw prices and fall through to the
European static-bounds filter. The tree's carry comes from the resolved
forward itself: r = -ln(D)/t and q = r - ln(F/spot)/t.

Wing filter (the Phase-3 "outlier filter" item): quotes further than
Z_MAX standard deviations from the forward, |k| > Z_MAX * sqrt(w_atm),
are excluded. Such options carry essentially no vega, so their implied
vols are numerically meaningless and would dominate max-IV-error
diagnostics without informing the fit (the synthetic 1M chain quotes
strikes out to ~6.5 sd, exactly this failure mode).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from volfit.api.session import QuoteEdit
from volfit.calib.band import DEFAULT_HAIRCUT, BandTarget, resolve_band
from volfit.core.american import deamericanize_batch
from volfit.core.black import black_call, implied_total_variance
from volfit.data.forwards import ImpliedForward, ResolvedForward
from volfit.data.types import ChainSnapshot

#: Wing cutoff in ATM standard deviations: quotes beyond this carry no vega
#: (at 1M a 5 sd strike has vega ~1e-6 — its implied vol is pure noise; 4 sd
#: matches the realistically quoted range and keeps every slice < 30 vol bp).
Z_MAX = 4.0


@dataclass(frozen=True)
class PreparedQuotes:
    """Fit inputs and display bands for one (ticker, expiry) slice.

    Arrays are aligned and sorted by k; only strikes with a full finite
    (bid, mid, ask) implied-vol band are kept. `n_deamericanized` counts the
    quotes whose early-exercise premium was stripped before inversion
    (always 0 for European snapshots).
    """

    t: float
    forward: float
    discount: float
    k: np.ndarray
    w_mid: np.ndarray  # total variance at mid, the calibration target
    iv_bid: np.ndarray
    iv_mid: np.ndarray
    iv_ask: np.ndarray
    n_deamericanized: int = 0


def _early_exercise_premiums(
    spot: float,
    is_call: np.ndarray,
    strikes: np.ndarray,
    k: np.ndarray,
    mids: np.ndarray,
    f: float,
    d: float,
    t: float,
    cash_dividends: tuple[np.ndarray, np.ndarray, float] | None = None,
) -> tuple[np.ndarray, int]:
    """Per-quote EEP implied by de-Americanizing the mids (see module doc).

    Returns (eep array, number of quotes successfully de-Americanized); the
    EEP is 0 wherever the tree inversion fails (nan sigma), so those quotes
    pass through unadjusted. With ``cash_dividends`` (ex-times, scaled amounts,
    rate) the de-Am uses a discrete escrowed CASH schedule and physical rate
    instead of the flat carry — modelling the real ex-date early-exercise
    asymmetry that the continuous-yield approximation smears into an ATM kink.
    """
    if cash_dividends is not None:
        div_t, div_a, r = cash_dividends  # discrete cash + physical rate, q = 0
        q = 0.0
    else:
        r = -float(np.log(d)) / t
        q = r - float(np.log(f / spot)) / t
        div_t = div_a = None
    sigma = deamericanize_batch(
        is_call, mids, spot, strikes, t, r, q, div_times=div_t, div_amounts=div_a
    )
    eep = np.zeros_like(mids)
    ok = np.isfinite(sigma)
    if ok.any():
        # European mid at the de-Americanized sigma, via the normalized Black
        # call and parity (puts): price = D F c for calls, D F (c - 1 + e^k).
        c_norm = black_call(k[ok], sigma[ok] ** 2 * t)
        european = d * f * np.where(is_call[ok], c_norm, c_norm - 1.0 + np.exp(k[ok]))
        eep[ok] = np.maximum(mids[ok] - european, 0.0)
    return eep, int(ok.sum())


def prepare_quotes(
    snapshot: ChainSnapshot,
    expiry: date,
    forward: ResolvedForward | ImpliedForward,
    t: float,
    cash_dividends: tuple[np.ndarray, np.ndarray, float] | None = None,
) -> PreparedQuotes:
    """Turn one expiry of a chain into sorted (k, w, IV-band) fit inputs.

    ``cash_dividends`` (ex-times, scaled amounts, rate) routes American de-
    Americanization through a discrete escrowed CASH schedule (volfit.api.state
    builds it forward-consistently); None keeps the continuous-yield carry.
    """
    f, d = forward.forward, forward.discount
    scale = 1.0 / (d * f)

    # Raw rows first: (k, strike, is_call, bid, mid, ask) in price space —
    # de-Americanization needs strikes and option types before normalization.
    rows: list[tuple[float, float, bool, float, float, float]] = []
    for quote in snapshot.quotes_for(expiry):
        if quote.bid is None or quote.ask is None or quote.mid is None:
            continue
        if quote.call_put != ("C" if quote.strike >= f else "P"):
            continue  # keep the OTM side only
        k = float(np.log(quote.strike / f))
        rows.append((k, quote.strike, quote.call_put == "C", quote.bid, quote.mid, quote.ask))

    if not rows:  # real providers can serve one-sided-only expiries
        raise ValueError(f"no two-sided OTM quotes for expiry {expiry.isoformat()}")
    rows.sort(key=lambda r: r[0])
    k_arr = np.array([r[0] for r in rows])
    strikes = np.array([r[1] for r in rows])
    is_call = np.array([r[2] for r in rows], dtype=bool)
    bid = np.array([r[3] for r in rows])
    mid = np.array([r[4] for r in rows])
    ask = np.array([r[5] for r in rows])

    # American chains: strip the early-exercise premium from bid/mid/ask.
    n_deam = 0
    if snapshot.exercise_style == "american" and t > 0.0:
        eep, n_deam = _early_exercise_premiums(
            snapshot.spot, is_call, strikes, k_arr, mid, f, d, t, cash_dividends
        )
        bid, mid, ask = bid - eep, mid - eep, ask - eep

    # European pipeline: normalize, parity-shift puts, invert to variance.
    shift = np.where(is_call, 0.0, 1.0 - np.exp(k_arr))
    w_bid = implied_total_variance(k_arr, bid * scale + shift)
    w_mid = implied_total_variance(k_arr, mid * scale + shift)
    w_ask = implied_total_variance(k_arr, ask * scale + shift)

    keep = np.isfinite(w_bid) & np.isfinite(w_mid) & np.isfinite(w_ask)
    if not keep.any():
        raise ValueError(f"no quotes inside static bounds for {expiry.isoformat()}")
    # Wing filter: estimate ATM total variance from the surviving mids, then
    # drop strikes more than Z_MAX standard deviations from the forward.
    w_atm = float(np.interp(0.0, k_arr[keep], w_mid[keep]))
    keep &= np.abs(k_arr) <= Z_MAX * np.sqrt(w_atm)
    return PreparedQuotes(
        t=t,
        forward=f,
        discount=d,
        k=k_arr[keep],
        w_mid=w_mid[keep],
        iv_bid=np.sqrt(w_bid[keep] / t),
        iv_mid=np.sqrt(w_mid[keep] / t),
        iv_ask=np.sqrt(w_ask[keep] / t),
        n_deamericanized=n_deam,
    )


def apply_edits(
    prepared: PreparedQuotes, edits: dict[int, QuoteEdit], weights: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """(k, w_mid, weights) calibration inputs after a session's quote edits.

    Excluded quotes are masked out; amended quotes get w = mid_iv^2 * t.
    `prepared` itself is untouched: the payload keeps showing every quote and
    the display grid stays on the full prepared k range while editing.
    Weights for "bidask"/"haircut" keep using the original market spread
    (amend only moves the mid level); they are just masked along with k.

    Edit indices beyond the prepared array are silently skipped: a forward-
    policy change can shrink the array (different OTM split / bound filter)
    while an old session still holds higher indices — dropping such stale
    edits is the robust choice over erroring a whole fit.
    """
    if not edits:
        return prepared.k, prepared.w_mid, weights
    w = prepared.w_mid.copy()
    keep = np.ones(prepared.k.size, dtype=bool)
    for index, edit in edits.items():
        if index >= prepared.k.size:
            continue  # stale index from a previous forward mode; see docstring
        if edit.amended_iv is not None:
            w[index] = edit.amended_iv**2 * prepared.t
        if edit.excluded:
            keep[index] = False
    return prepared.k[keep], w[keep], None if weights is None else weights[keep]


def apply_band_edits(
    prepared: PreparedQuotes,
    edits: dict[int, QuoteEdit],
    fit_mode: str,
    haircut: float = DEFAULT_HAIRCUT,
) -> BandTarget | None:
    """Band target aligned with ``apply_edits`` (same exclude/amend/keep mask).

    Amended quotes move the mid (and hence the haircut band, which is built
    around mid); the bid/ask edges stay the original market band. The keep mask
    matches ``apply_edits`` exactly, so the band rows line up with (k, w).
    Returns None for the "mid" mode (no band objective).
    """
    if fit_mode == "mid":
        return None
    iv_bid = prepared.iv_bid.copy()
    iv_mid = prepared.iv_mid.copy()
    iv_ask = prepared.iv_ask.copy()
    keep = np.ones(prepared.k.size, dtype=bool)
    for index, edit in edits.items():
        if index >= prepared.k.size:
            continue
        if edit.amended_iv is not None:
            iv_mid[index] = edit.amended_iv
        if edit.excluded:
            keep[index] = False
    return resolve_band(iv_bid[keep], iv_mid[keep], iv_ask[keep], fit_mode, haircut)
