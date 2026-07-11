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

When a reference date is supplied for an American snapshot, ``_refine_american``
de-biases the forward AND — when needed — the discount ([REQ 2026-07-11], the
SPY 17-Jun-27 kink; this is the joint borrow/de-Americanization fixed point the
carry roadmap deferred to R2). The raw parity SLOPE is contaminated by the
K-dependence of the early-exercise premium difference (ITM-put EEP grows with
K), and on a long-dated chain the bias is large enough to flip the implied rate
NEGATIVE (observed live: D = 1.0039 at 0.93y, r = -0.41%, structured parity
residuals of +$9..$15). Under a negative rate and the resulting negative carry
the binomial model prices ZERO early-exercise premium on both sides, so the
old forward-only de-bias had nothing to act on and the smile kept a ~28 vol-bp
jump at the money.

The refinement therefore treats the de-Americanized put/call IV gap at the
money — the user-visible defect — as the estimating equation for the rate:
European calls and puts at the same strike share one Black vol, so at the
correct (r, F) the de-Americanized sides JOIN. The gap is monotone in the
assumed rate (a higher r prices more put EEP and less call EEP), so a bounded
bisection inside the physical band [RATE_MIN, RATE_MAX] finds the rate that
zeroes it; each candidate re-runs the forward fixed point below. Chains whose
sides already join within GAP_TOL_VOL keep the raw regressed discount and the
forward-only behavior bit-for-bit (short-dated chains: EEP ~ 0 makes the rate
unidentifiable AND the kink invisible — exactly the cases to leave alone).
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

#: Joint rate refinement ([REQ 2026-07-11], the SPY 17-Jun-27 kink): when the
#: de-Americanized put and call IV sides fail to join at the money by more than
#: GAP_TOL_VOL (vol units) under the raw parity discount, the rate is re-implied
#: by bisecting the (monotone) gap to zero inside [RATE_MIN, RATE_MAX]. Below
#: the tolerance — every clean or short-dated chain — the raw discount and the
#: forward-only refinement are kept bit-for-bit.
GAP_TOL_VOL = 5e-4  # 5 vol bp: an ATM side gap below this is invisible
GAP_BISECT_ITERS = 24  # bisection cap (band 35% wide -> sub-bp rate resolution)
GAP_RATE_TOL = 1e-4  # stop when the rate bracket is 1 bp wide
#: The switch gap is LOCAL: the per-strike de-Am'd call-put IV difference is a
#: steep, nearly linear function of K (a discount error tilts it at ~1 bp/$ on
#: live SPY), so it must be read AT the forward — a Gaussian kernel of this
#: log-moneyness bandwidth around F (a wide-band mean cancels to ~0 by symmetry
#: and a wide-band line fit is leveraged by wing structure; both were measured
#: to miss the ~25 bp ATM signal on the live chain). The bandwidth is TIGHT —
#: at 1% it spans only the couple of strikes straddling the switch — because a
#: wider kernel leaks the gap-line SLOPE into the read through asymmetric
#: strike coverage around F and biases the implied rate upward (measured:
#: bw 0.02 rooted at r 6.2% where the strictly local pair measure roots 4.5%).
GAP_KERNEL_H = 0.01
#: The gap must also be measured at FULL tree depth: the coarse 48-step tree
#: carries a systematic ~40 vol-bp call-put inversion asymmetry (odd/even strike
#: lattice alignment that does not cancel between the sides), which buries the
#: signal and even flips its monotonicity in r. Full depth per gap evaluation is
#: affordable since the Numba CRR kernel (core.american_numba); the always-run
#: forward-only fixed point keeps the coarse tree so chains below the gate stay
#: bit-for-bit on the historical path.
GAP_TREE_STEPS = 192
GAP_TREE_BISECT = 24


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
) -> tuple[float, float, float] | None:
    """De-bias the forward — and, when the sides fail to join, the discount.

    Returns (F, D, european-rms) or None. Per candidate rate r (carry
    q = r - ln(F/S)/t from the current forward), the call and put mids are
    de-Americanized to European-equivalent Black vols, repriced as European
    calls (puts by parity) and the forward re-implied at the fixed slope
    -e^{-rt} (F = mean(y + D K)/D) to its fixed point — exactly the carry
    quote prep uses downstream.

    European calls and puts at one strike share one Black vol, so the
    de-Americanized IV side gap sigma_c - sigma_p, read AT the forward with a
    tight ATM kernel (GAP_KERNEL_H), measures the ATM kink directly. Under the
    raw parity discount a gap within GAP_TOL_VOL keeps that discount
    bit-for-bit (the historical forward-only behavior); a larger gap
    re-implies the rate by bisecting the (monotone-decreasing) gap to zero
    inside [RATE_MIN, RATE_MAX] — the raw slope is EEP-contaminated on exactly
    these chains (module docstring). No bracketing sign change -> the raw
    discount is kept (never extrapolate outside the physical band).

    Only the near-ATM band of strikes enters (DEAM_REFINE_BAND). The always-run
    forward-only fixed point keeps the historical coarse tree (bit-identical
    below the gate); the gate and the rate search price at full depth, where
    the gap signal beats the lattice noise (GAP_TREE_STEPS comment). Quote prep
    keeps doing the full-precision per-quote de-Am downstream.
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
    f_init = forward

    def evaluate(r: float, steps: int, bisect: int) -> tuple[float, float, float] | None:
        """Forward fixed point at rate r: (F, rms, mean IV side gap) or None.

        ``steps``/``bisect`` set the de-Am tree depth: coarse for the always-run
        forward-only path (the historical, bit-identical behavior), full depth
        for the gate/bisection where the gap signal must beat the lattice noise
        (GAP_TREE_STEPS comment)."""
        d = math.exp(-r * t)
        f = f_init
        rms = gap = float("nan")
        for _ in range(MAX_DEAM_ITERS):
            q = r - float(np.log(f / spot)) / t
            sigma_c = deamericanize_batch(
                is_call, call_mids, spot, strikes, t, r, q, steps, bisect
            )
            sigma_p = deamericanize_batch(
                is_put, put_mids, spot, strikes, t, r, q, steps, bisect
            )
            ok = np.isfinite(sigma_c) & np.isfinite(sigma_p)
            if int(ok.sum()) < MIN_PAIRED_STRIKES:
                return None  # too few invertible pairs to trust the de-biased fit
            # Switch gap: the de-Am'd call-put IV difference READ AT the forward
            # (ATM kernel) — the jump the smile shows where OTM sides swap.
            w_atm = np.exp(-((np.log(strikes[ok] / f) / GAP_KERNEL_H) ** 2))
            gap = float(np.sum(w_atm * (sigma_c[ok] - sigma_p[ok])) / np.sum(w_atm))
            # European-equivalent prices via normalized Black (the exact map quote
            # prep inverts): call = D F c, put = D F (c - 1 + e^k).
            k = np.log(strikes / f)
            eur_c = d * f * black_call(k, sigma_c**2 * t)
            eur_p = d * f * (black_call(k, sigma_p**2 * t) - 1.0 + np.exp(k))
            # Re-imply the forward at the FIXED slope -D: y = D (F - K) => F below.
            y = (eur_c - eur_p)[ok]
            k_ok = strikes[ok]
            new_f = float(np.mean(y + d * k_ok) / d)
            residuals = y - d * (new_f - k_ok)
            rms = float(np.sqrt(np.mean(residuals * residuals)))
            converged = abs(new_f - f) <= FORWARD_TOL_REL * f
            f = new_f
            if converged:
                break
        return f, rms, gap

    def switch_gap_at(r: float, f: float) -> float:
        """Full-depth switch gap with F HELD at ``f`` (no refit) — reads the kink
        quote prep would actually display under (r, f)."""
        q = r - float(np.log(f / spot)) / t
        sigma_c = deamericanize_batch(
            is_call, call_mids, spot, strikes, t, r, q, GAP_TREE_STEPS, GAP_TREE_BISECT
        )
        sigma_p = deamericanize_batch(
            is_put, put_mids, spot, strikes, t, r, q, GAP_TREE_STEPS, GAP_TREE_BISECT
        )
        ok = np.isfinite(sigma_c) & np.isfinite(sigma_p)
        if int(ok.sum()) < MIN_PAIRED_STRIKES:
            return float("nan")
        w_atm = np.exp(-((np.log(strikes[ok] / f) / GAP_KERNEL_H) ** 2))
        return float(np.sum(w_atm * (sigma_c[ok] - sigma_p[ok])) / np.sum(w_atm))

    r_raw = -float(np.log(discount)) / t
    base = evaluate(r_raw, DEAM_REFINE_STEPS, DEAM_REFINE_BISECT)
    if base is None:
        return None
    f_raw, rms_raw, _ = base
    # Gate on the kink the pipeline would DISPLAY: full depth, at the coarse
    # path's own forward (the F-refit inside ``evaluate`` partially masks it).
    gate_gap = switch_gap_at(r_raw, f_raw)
    if not np.isfinite(gate_gap) or abs(gate_gap) <= GAP_TOL_VOL:
        return f_raw, discount, rms_raw  # sides join: raw discount, old behavior

    # The gap (with the forward re-fit per candidate) decreases in r — a higher
    # rate prices more put EEP and less call EEP — so bracket toward the band
    # edge on the gap's side and bisect. Everything stays inside the physical
    # rate band; no sign change there -> keep the raw fit.
    start = evaluate(r_raw, GAP_TREE_STEPS, GAP_TREE_BISECT)
    if start is None or not np.isfinite(start[2]):
        return f_raw, discount, rms_raw
    gap0 = start[2]
    if abs(gap0) <= GAP_TOL_VOL:
        # The raw rate already reconciles the sides once the forward is re-fit
        # at full depth: the displayed kink was the coarse forward's error.
        return start[0], discount, start[1]
    r_edge = RATE_MAX if gap0 > 0.0 else RATE_MIN
    edge = evaluate(r_edge, GAP_TREE_STEPS, GAP_TREE_BISECT)
    if edge is None or not np.isfinite(edge[2]) or edge[2] * gap0 >= 0.0:
        return f_raw, discount, rms_raw
    lo, hi = (r_raw, r_edge) if gap0 > 0.0 else (r_edge, r_raw)
    r_best, best = r_raw, start
    for _ in range(GAP_BISECT_ITERS):
        mid = 0.5 * (lo + hi)
        cand = evaluate(mid, GAP_TREE_STEPS, GAP_TREE_BISECT)
        if cand is None or not np.isfinite(cand[2]):
            return f_raw, discount, rms_raw  # inversion degraded mid-search
        r_best, best = mid, cand
        # The gap is FLAT near the root (~1 bp per 1% of rate), so the stop must
        # be tight — a loose tolerance admits a multi-percent rate window.
        if abs(cand[2]) <= 0.2 * GAP_TOL_VOL or hi - lo <= GAP_RATE_TOL:
            break
        if cand[2] > 0.0:
            lo = mid
        else:
            hi = mid
    f_star, rms_star, _ = best
    return f_star, math.exp(-r_best * t), rms_star


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

    # American de-bias: nudge the forward — and, when the de-Americanized put
    # and call sides still fail to join at the money, the discount too (the raw
    # parity slope is EEP-contaminated on exactly those chains; module doc) —
    # so the two OTM sides meet at the switch strike.
    if snapshot.exercise_style == "american" and reference_date is not None:
        t = (expiry - reference_date).days / 365.0
        if t > 0.0 and discount > 0.0:
            refined = _refine_american(
                snapshot.spot, strikes[active], c[active], p[active], t, forward, discount
            )
            if refined is not None:
                forward, discount, rms = refined

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
