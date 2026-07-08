"""Implied forwards via put-call parity regression.

Design intent (ROADMAP Phase 3, decision recorded there): forwards are
implied *robustly from quotes* before any model is fitted — explicit
dividend curves come later as a fallback.  For each expiry, parity gives

    C(K) - P(K) = D (F - K),

linear in K.  Regressing y = C_mid - P_mid on K by least squares,

    y = a + b K   with   a = D F,  b = -D
    =>  D = -b,   F = a / D,

which uses every paired strike at once and averages out quote noise.  The
residual RMS of the regression is reported as a quality diagnostic; expiries
with fewer than three paired strikes (or a non-positive implied discount)
are skipped — too little data to trust a two-parameter fit.

Stale-quote robustness ([REQ 2026-06-12]): live chains carry stale deep-wing
mids whose parity residuals are dollars, not cents (observed rms 2-30 on a
few live expiries), and plain least squares lets one such pair tilt the
whole forward.  The regression therefore iterates: fit, measure residuals,
drop pairs beyond OUTLIER_NSIGMA robust standard deviations (1.4826 x MAD,
floored at OUTLIER_FLOOR_BP of spot so clean tight chains never trim), and
refit — at most MAX_TRIM_ROUNDS rounds and never below MIN_PAIRED_STRIKES
survivors.  Dropped pairs are reported as ``n_outliers``.

Discount clamp ([REQ 2026-06-25], robustness to noisy/stale feeds): the parity
SLOPE *is* the discount, the worst-identified parameter, and on a noisy/stale live
feed (a delayed tier with wide deep-ITM quotes) it drifts to nonsense — observed
implied discount > 1, a negative rate, which tilts the whole forward and gaps the
displayed smile at the money. So when a reference date is supplied (the fitting path),
the implied discount is **clamped to a physical rate band** [RATE_MIN, RATE_MAX]:
clean chains sit well inside it and are byte-for-byte unchanged; only an absurd
discount is bounded. When the clamp bites, the forward is **re-derived from the
well-identified level** — a spread + ATM weighted mean of K + (C-P)/D (tight,
near-the-money pairs, where parity is cleanest and both legs are liquid, dominate) —
so it no longer inherits the bad slope (F = intercept/slope).

Zero-carry synthesized chains ([REQ 2026-07-08], the SPY forward incident):
a delayed data tier can gate NBBO quotes, and the provider then SYNTHESIZES the
chain from its per-contract IVs, pricing every contract with Black at F = spot,
D = 1, zero spread (volfit.data.massive._chain_from_ivs). Those prices carry no
parity information — the provider's call/put IVs embed its OWN carry model, so
regressing the zero-carry re-prices reads the call/put IV asymmetry as a
spurious forward and discount (observed live on SPY: -3.8% short-dated implied
rates, D > 1, and a one-year forward +1.7% above the F = spot the prices were
built with — inside the discount clamp's rate band, so the clamp is silent).
`implied_forward` therefore returns the chain's own construction convention
(F = spot, D = 1, rms 0) for such chains, via the snapshot's explicit
``zero_carry`` flag (persisted with the snapshot, store schema v5). The flag is
deliberately NOT inferred from chain-wide zero spreads: EOD close marks also
quote bid == ask yet their mids carry genuine parity information.

American de-biasing (fixes the ATM smile kink): put-call parity is an
*equality* only for European options.  American C - P carries the difference
of the call and put early-exercise premiums, so a forward implied from RAW
American mids is biased (~40 bp observed).  Quote prep then de-Americanizes
OTM puts (left of the forward) and OTM calls (right of it) under the resulting
carry, pushing the two sides in OPPOSITE directions: a visible implied-vol
jump straight at the money.

When a reference date is supplied for an American snapshot we de-bias *only
the forward*, holding the parity DISCOUNT at its raw regressed value
(``_refine_american``).  This is deliberate: the discount is the regression
SLOPE, poorly identified on short-dated narrow-strike chains, and re-implying
it from de-Americanized prices is numerically fragile — on live SPY it drifted
to implausible rates (a 5% discount error shifts the whole IV level through
the 1/(D F) normalization).  The forward (the intercept-driven LEVEL) is
robust, and the kink is driven by the carry q = r - ln(F/S)/t, i.e. by the
forward.  So we iterate the carry's q via the forward to the fixed point that
reconciles the de-Americanized puts and calls, leaving the discount exactly as
the existing pipeline already used it — no IV-level regression, the kink gone.
Discrete-dividend chains can retain a small residual kink (the tree uses a
continuous yield); discrete-dividend de-Americanization is future work.
European snapshots and the no-reference path are byte-for-byte unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np

from volfit.core.american import deamericanize_batch
from volfit.core.black import black_call
from volfit.data.types import ChainSnapshot

#: Minimum number of strikes with both call and put mids for a valid fit.
MIN_PAIRED_STRIKES = 3

#: Outlier rejection: drop parity pairs beyond this many robust sigmas …
OUTLIER_NSIGMA = 4.0
#: … with the robust sigma floored at this fraction of spot (1 bp), so a
#: clean chain whose residuals are all sub-cent never trims anything.
OUTLIER_FLOOR_BP = 1e-4
#: Trim/refit rounds (each round can only shrink the active set).
MAX_TRIM_ROUNDS = 3

#: Discount clamp (robustness to noisy/stale feeds, when a reference date is given).
#: The parity SLOPE *is* the discount — the worst-identified parameter — and on real
#: delayed feeds it drifts to nonsense (observed D > 1, a negative implied rate, which
#: tilts the forward and gaps the smile at the money). The implied discount is clamped
#: to the physical rate band [RATE_MIN, RATE_MAX]; clean chains sit inside it untouched.
#: When the clamp bites, the forward is re-derived from the well-identified level by a
#: spread + ATM weighted mean of K + (C-P)/D (tight near-the-money pairs dominate).
RATE_MIN, RATE_MAX = -0.05, 0.30  # physical bounds on the parity-implied discount's rate
ATM_KERNEL_H = 0.10  # ATM Gaussian bandwidth (log-moneyness) for the re-derived forward
SPREAD_FLOOR_FRAC = 5e-4  # inverse-spread weight floor, as a fraction of spot
FWD_CLAMP_LOG = 0.5  # forward sanity bound |ln(F/S)|; beyond it, fall back to spot

#: American de-bias fixed-point iteration: re-imply the forward from
#: de-Americanized mids until F moves less than FORWARD_TOL_REL (relative),
#: or MAX_DEAM_ITERS rounds. Convergence is geometric (~halving per round),
#: so the cap is a safety net; the kink is gone within a couple of rounds.
MAX_DEAM_ITERS = 6
FORWARD_TOL_REL = 5e-5

#: De-bias de-Americanization is deliberately COARSE — it only has to locate
#: the forward to ~1 bp, not price to the last cent — so the bootstrap stays
#: cheap (the precise per-quote de-Am happens later in quote prep). A shallow
#: tree, few bisections and only the near-ATM band (where parity is cleanest
#: and the tree inverts fastest) cut it from seconds to a few ms per expiry.
DEAM_REFINE_STEPS = 48
DEAM_REFINE_BISECT = 16
DEAM_REFINE_BAND = 0.15  # |log(K/F)| window of strikes used for the de-bias
DEAM_REFINE_MAX_STRIKES = 11  # cap the near-ATM set (averaging plateaus fast)


@dataclass(frozen=True)
class ImpliedForward:
    """Parity-implied forward and discount factor for one expiry."""

    expiry: date
    forward: float
    discount: float
    n_strikes: int
    residual_rms: float
    n_outliers: int = 0  # parity pairs dropped by the stale-quote filter


#: Where a fitting forward comes from ([REQ 2026-06-12] forward modes):
#: the parity regression above, the dividend-model theoretical forward
#: (volfit.data.dividends), or a user-entered manual override.
ForwardSource = Literal["parity", "theoretical", "manual"]


@dataclass(frozen=True)
class ResolvedForward:
    """The (forward, discount) pair calibration actually uses for one expiry.

    Quote prep only needs `.forward`/`.discount`, so an `ImpliedForward` and
    a `ResolvedForward` are interchangeable there; `source` records which
    `ForwardSource` the per-expiry policy selected (diagnostics/UI).
    """

    expiry: date
    forward: float
    discount: float
    source: str  # a ForwardSource value


def _fit(k: np.ndarray, v: np.ndarray) -> tuple[float, float, np.ndarray]:
    """Least squares v = a + b k; returns (a, b, residuals)."""
    design = np.column_stack([np.ones_like(k), k])
    (a, b), *_ = np.linalg.lstsq(design, v, rcond=None)
    return float(a), float(b), v - (a + b * k)


def _refine_american(
    spot: float,
    strikes: np.ndarray,
    call_mids: np.ndarray,
    put_mids: np.ndarray,
    t: float,
    forward: float,
    discount: float,
) -> tuple[float, float] | None:
    """De-bias the forward (discount held), returning (F, european-rms) or None.

    The rate r = -ln(D)/t is fixed from the raw parity discount; each round
    sets the carry q = r - ln(F/S)/t from the current forward, de-Americanizes
    the call and put mids to European-equivalent Black vols, reprices them as
    European calls (puts by parity) and re-implies the forward at the FIXED
    slope -D (F = mean(y + D K)/D). Iterating moves q to the fixed point that
    reconciles the de-Americanized puts and calls — exactly the carry quote
    prep uses — so the two OTM sides join, with the discount left untouched.

    Only the near-ATM band of strikes enters (DEAM_REFINE_BAND), with a coarse
    tree: it locates the forward to ~1 bp in a few ms, while quote prep keeps
    doing the full-precision per-quote de-Am downstream.
    """
    # Near-ATM subset (selected once from the initial forward): cheapest and
    # most reliable strikes for the de-bias.
    band = np.abs(np.log(strikes / forward))
    near = band <= DEAM_REFINE_BAND
    if int(near.sum()) < MIN_PAIRED_STRIKES:  # fall back to the nearest strikes
        near = np.zeros(strikes.size, dtype=bool)
        near[np.argsort(band)[:DEAM_REFINE_MAX_STRIKES]] = True
    elif int(near.sum()) > DEAM_REFINE_MAX_STRIKES:
        keep_idx = np.nonzero(near)[0][np.argsort(band[near])[:DEAM_REFINE_MAX_STRIKES]]
        near = np.zeros(strikes.size, dtype=bool)
        near[keep_idx] = True
    strikes, call_mids, put_mids = strikes[near], call_mids[near], put_mids[near]

    is_call = np.ones(strikes.size, dtype=bool)
    is_put = np.zeros(strikes.size, dtype=bool)
    r = -float(np.log(discount)) / t  # fixed: the raw parity discount's rate
    rms = float("nan")
    for _ in range(MAX_DEAM_ITERS):
        q = r - float(np.log(forward / spot)) / t
        sigma_c = deamericanize_batch(
            is_call, call_mids, spot, strikes, t, r, q, DEAM_REFINE_STEPS, DEAM_REFINE_BISECT
        )
        sigma_p = deamericanize_batch(
            is_put, put_mids, spot, strikes, t, r, q, DEAM_REFINE_STEPS, DEAM_REFINE_BISECT
        )
        ok = np.isfinite(sigma_c) & np.isfinite(sigma_p)
        if int(ok.sum()) < MIN_PAIRED_STRIKES:
            return None  # too few invertible pairs to trust the de-biased fit
        # European-equivalent prices via normalized Black (the exact map quote
        # prep inverts): call = D F c, put = D F (c - 1 + e^k).
        k = np.log(strikes / forward)
        eur_c = discount * forward * black_call(k, sigma_c**2 * t)
        eur_p = discount * forward * (black_call(k, sigma_p**2 * t) - 1.0 + np.exp(k))
        # Re-imply the forward at the FIXED slope -D: y = D (F - K) => F below.
        y = (eur_c - eur_p)[ok]
        k_ok = strikes[ok]
        new_forward = float(np.mean(y + discount * k_ok) / discount)
        residuals = y - discount * (new_forward - k_ok)
        rms = float(np.sqrt(np.mean(residuals * residuals)))
        converged = abs(new_forward - forward) <= FORWARD_TOL_REL * forward
        forward = new_forward
        if converged:
            break
    return forward, rms


def _quality_weights(
    strikes: np.ndarray, spread_c: np.ndarray, spread_p: np.ndarray, spot: float
) -> np.ndarray:
    """Per-pair trust weight: inverse combined bid-ask spread x ATM Gaussian kernel.

    Tight, near-the-money pairs — where put-call parity is cleanest and both legs
    are liquid — dominate; the wide/stale or deep-wing pairs that tilt a plain
    equal-weight regression are damped. Zero-spread (close-like) data, which carries
    no spread signal, falls back to the ATM kernel alone."""
    spread = np.maximum(spread_c, 0.0) + np.maximum(spread_p, 0.0)
    inv_spread = 1.0 / (spread + SPREAD_FLOOR_FRAC * spot)
    kern = np.exp(-((np.log(strikes / spot) / ATM_KERNEL_H) ** 2))
    return inv_spread * kern


def _forward_at_discount(
    strikes: np.ndarray, c: np.ndarray, p: np.ndarray,
    spread_c: np.ndarray, spread_p: np.ndarray, spot: float, discount: float,
) -> float:
    """Forward at a FIXED discount, from the well-identified LEVEL: a spread/ATM-
    weighted mean of the per-strike F_i = K + (C-P)/D. Used after the parity slope
    is clamped, so the forward no longer inherits the bad slope (F = intercept/slope).
    Tight near-the-money pairs dominate; an absurd result falls back to spot."""
    w = _quality_weights(strikes, spread_c, spread_p, spot)
    f_i = strikes + (c - p) / discount
    wsum = float(np.sum(w))
    forward = float(np.sum(w * f_i) / wsum) if wsum > 0.0 else spot
    if not (np.isfinite(forward) and forward > 0.0) or abs(math.log(forward / spot)) > FWD_CLAMP_LOG:
        return spot
    return forward


def implied_forward(
    snapshot: ChainSnapshot, expiry: date, reference_date: date | None = None,
) -> ImpliedForward | None:
    """Imply the forward for one expiry, or None if the data is insufficient.

    Only strikes carrying *both* a usable call mid and put mid enter the
    regression; one-sided or crossed quotes are excluded via `OptionQuote.mid`.
    For an American snapshot, pass ``reference_date`` to de-bias the forward
    (see the module docstring); without it the raw-mid regression is used.
    """
    call: dict[float, tuple[float, float]] = {}  # strike -> (mid, spread)
    put: dict[float, tuple[float, float]] = {}
    for quote in snapshot.quotes_for(expiry):
        mid = quote.mid
        if mid is None:
            continue
        spread = quote.spread if (quote.spread is not None and quote.spread > 0.0) else 0.0
        (call if quote.call_put == "C" else put)[quote.strike] = (mid, spread)

    paired = sorted(set(call) & set(put))
    if len(paired) < MIN_PAIRED_STRIKES:
        return None

    # Zero-carry synthesized chains (a delayed tier's IV fallback: every price
    # is Black at F = spot, D = 1, zero spread) carry NO parity information —
    # the provider's call/put IVs embed ITS carry model, so regressing their
    # zero-carry re-prices reads that asymmetry as a spurious forward/discount
    # (observed live on SPY: -3.8% short rates, a +1.7% one-year forward).
    # The honest parity answer is the chain's own construction convention.
    if snapshot.is_zero_carry():
        return ImpliedForward(
            expiry=expiry, forward=snapshot.spot, discount=1.0,
            n_strikes=len(paired), residual_rms=0.0,
        )

    strikes = np.array(paired)
    c = np.array([call[s][0] for s in paired])
    p = np.array([put[s][0] for s in paired])
    spread_c = np.array([call[s][1] for s in paired])
    spread_p = np.array([put[s][1] for s in paired])
    y = c - p

    # Equal-weight parity regression + stale-quote outlier trim.
    active = np.ones(strikes.size, dtype=bool)
    a, b, residuals = _fit(strikes, y)
    for _ in range(MAX_TRIM_ROUNDS):
        scale = max(
            1.4826 * float(np.median(np.abs(residuals))),  # robust sigma (MAD)
            OUTLIER_FLOOR_BP * snapshot.spot,
        )
        keep = np.abs(residuals) <= OUTLIER_NSIGMA * scale
        if keep.all() or keep.sum() < MIN_PAIRED_STRIKES:
            break
        active[np.nonzero(active)[0][~keep]] = False
        a, b, residuals = _fit(strikes[active], y[active])
    discount = -b
    if discount <= 0.0 and snapshot.exercise_style != "american":
        return None  # nonsensical fit (e.g. corrupt quotes)
    forward = a / discount if discount != 0.0 else float("nan")
    rms = float(np.sqrt(np.mean(residuals * residuals)))

    # Clamp the discount to a physical rate band. The parity SLOPE is the discount,
    # the worst-identified parameter, and on noisy/stale wings (delayed feeds) it
    # drifts to D > 1 — a negative implied rate that tilts the forward and gaps the
    # smile at the money. Clean chains sit well inside the band and are untouched
    # (byte-identical); only an absurd discount is bounded, and the forward then
    # re-derived from the well-identified level so it no longer inherits the bad slope.
    if reference_date is not None:
        t = (expiry - reference_date).days / 365.0
        if t > 0.0 and np.isfinite(discount):
            d_clamped = min(max(discount, math.exp(-RATE_MAX * t)), math.exp(-RATE_MIN * t))
            if d_clamped != discount:
                discount = d_clamped
                forward = _forward_at_discount(
                    strikes[active], c[active], p[active],
                    spread_c[active], spread_p[active], snapshot.spot, discount
                )

    # American de-bias: nudge the forward (discount held) using de-Americanized
    # European-equivalent mids so the OTM put and call sides join at the money.
    if snapshot.exercise_style == "american" and reference_date is not None:
        t = (expiry - reference_date).days / 365.0
        if t > 0.0 and discount > 0.0:
            refined = _refine_american(
                snapshot.spot, strikes[active], c[active], p[active], t, forward, discount
            )
            if refined is not None:
                forward, rms = refined

    if discount <= 0.0 or not np.isfinite(forward):
        return None
    return ImpliedForward(
        expiry=expiry,
        forward=forward,
        discount=discount,
        n_strikes=int(active.sum()),
        residual_rms=rms,
        n_outliers=int((~active).sum()),
    )


def implied_forwards(
    snapshot: ChainSnapshot, reference_date: date | None = None,
) -> dict[date, ImpliedForward]:
    """Imply forwards for every expiry in the chain that has enough pairs.

    Pass ``reference_date`` (the fitting path does, via volfit.api.state) to
    de-bias American snapshots AND clamp the parity discount to a physical rate
    band — robust to the noisy/stale wings that otherwise drift it to D > 1.
    Without it the raw-mid regression is used (offline/backtest callers).
    """
    out: dict[date, ImpliedForward] = {}
    for expiry in snapshot.expiries():
        result = implied_forward(snapshot, expiry, reference_date)
        if result is not None:
            out[expiry] = result
    return out
