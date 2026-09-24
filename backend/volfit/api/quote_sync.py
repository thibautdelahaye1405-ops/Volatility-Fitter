"""Quote synchronisation: every quote brought to the chain's spot and time
before a calibration (QUOTE SYNC, 2026-09-24).

Why
---
A chain assembled from layers of different ages — live ticks at S_now, a
per-minute REST layer up to 60 s old at S_rest, Bloomberg paints, recorded
frames — is one set of prices quoted against DIFFERENT spots. Inverting a
quote that was quoted at spot S_i against today's forward F_now mis-reads its
implied vol by the price the forward move is worth, in vol units:

    Δσ ≈ Δ · ΔF / vega,   ΔF = F_now · (S_now − S_i) / S_now ;

for an ATM one-month option (Δ ≈ 0.5, vega ≈ F φ(0) √T ≈ 0.115 F) a 0.1 %
spot move reads as ~40 vol bp — an order of magnitude above the fit's
resolution. The live merge (2026-09-24b) fits a live core at S_now beside a
REST layer at S_rest without correcting for that; this step removes the bias
and, beyond it, lets any set of quotes of different ages (rotated buckets,
paints, recorded frames) be calibrated together as one synchronous set.

The method (``volfit.api.quotes.prepare_quotes`` calls these pieces in order)
-----------------------------------------------------------------------------
For a quote i at strike K with its own spot S_i and stamp t_i (a quote
without a spot / stamp of its own uses the chain's, i.e. is already
synchronous):

1. Its forward at its own spot, F_i = forward_at(S_i): the app's forward-
   transport rule from the chain's (S_now, F_now) — proportional
   F_i = F_now · S_i / S_now, or additive F_i = F_now + (S_i − S_now) e^{rT}
   under a discrete cash-dividend schedule (``service.spot_forward_shift``,
   passed in as the ``forward_at`` callable; ``row_forwards``).
2. Its PRICE is de-Americanized and Black-inverted at ITS forward: the quotes
   are grouped by distinct spot (few: the live layer, one REST layer, a
   handful of paints), the batch de-Am runs per group at that group's spot
   (``grouped_early_exercise_premiums``), and the inversion gives
   w_i^{bid,mid,ask} at k_i = ln(K / F_i).
3. Regime correction with the REFERENCE smile w0(k) — the node's last
   committed fit, as a total-variance function of k = ln(K / F_cal) — under
   the app's dynamics regime R (Note 12, eq. SSR: w~(k) = w0(k + R h); the
   exact-LV regimes use ``transported_w``'s own ℓ_T map). With
   h_i = ln(F_i / F_cal), h_now = ln(F_now / F_cal), x = k_i + R h_i and
   δ_i = ln(F_now / F_i):

       Δw_i = w0(x + (R − 1) δ_i) − w0(x)                     (``regime_shift``)

   = the reference transported to S_now, read at the quote's strike, minus
   the reference transported to S_i at the same strike — exactly 0 under
   sticky-strike (R = 1), the fixed-moneyness relabel under R = 0, the
   double-skew response under R = 2. Then w_sync = w_i + Δw_i for each of
   bid / mid / ask (the spread is kept in w) at k_sync = ln(K / F_now) =
   k_i − δ_i. Without a reference fit Δw = 0 (sticky-strike behaviour) and
   the prepared quotes record ``sync_reference = "none"``.
4. Time: total variance w is HELD across the age (the invariant over
   minutes); the fit's τ is the chain's (the intraday clock handles a
   same-day rung as today).
5. Age: age_i = t_now − t_i in minutes (t_now = the chain's stamp; 0 for a
   stored frame). The IV uncertainty of a quote that old is

       s_i = a · √age_i · (σ_atm / 0.15)                       (``age_widening``)

   with a = ``OptionsSettings.quoteSyncAgeBpPerSqrtMin`` (default 3.6 vol bp
   per √minute: the intraday campaign's SPY ATM drift of 19.5 vol bp per
   30 min, backtest/FINDINGS_observation_filter.md, scaled by the node's ATM
   vol relative to SPY's 15 %). Band / haircut modes widen the quote's IV band
   by s_i on each side (in w: w(σ ± s)); mid mode multiplies its weight by
   1 / (1 + (s_i / s_half,i)²), s_half,i the half-spread in IV floored at 1 bp
   (``age_weight_multiplier``; applied by ``quotes.apply_band_edits`` /
   ``quotes.apply_age_weights``).

Byte-identity: on a chain whose quotes all share the chain's spot and stamp
(every REST chain today) ``needs_sync`` is False, nothing here runs and the
prepared arrays are byte-identical with the feature on or off.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

import numpy as np

from volfit.core.black import W_MIN
from volfit.data.types import ChainSnapshot, OptionQuote
from volfit.dynamics.ssr import ssr_of_regime
from volfit.dynamics.transport import is_exact_lv, transported_w

#: The ATM vol the campaign's age number is quoted at (SPY, 15 %): the age
#: uncertainty scales with the node's ATM vol relative to it.
AGE_SIGMA_REF = 0.15

#: Default age uncertainty, vol bp per √minute: 19.5 vol bp per 30 min ⇒
#: 19.5 / √30 ≈ 3.6 (the SPY intraday campaign, FINDINGS_observation_filter).
DEFAULT_AGE_BP_PER_SQRT_MIN = 3.6

#: Floor of the half-spread in IV the mid-mode age weight compares s_i to
#: (1 vol bp): a zero-spread mark must not collapse every stale weight to 0.
HALF_SPREAD_FLOOR = 1e-4


@dataclass(frozen=True)
class SyncContext:
    """What one slice's synchronisation needs from the app (built by
    ``service.sync_context``): the forward-transport rule, the dynamics
    regime, the reference smile (None = no committed fit) and the age scale."""

    #: spot -> forward at that spot, the app's rule from the chain's (S, F).
    forward_at: Callable[[float], float]
    #: The dynamics regime R (a named regime or a numeric SSR).
    regime: str | float
    #: The reference total variance w0(k), k = ln(K / F_cal); None = no fit.
    reference_w: Callable[[np.ndarray], np.ndarray] | None = None
    #: The reference fit's forward F_cal.
    reference_forward: float | None = None
    #: The reference fit's ATM vol (the age scale); None = the chain's own.
    sigma_atm: float | None = None
    #: a, vol bp per √minute (0 = no widening / no down-weighting).
    age_bp_per_sqrt_min: float = DEFAULT_AGE_BP_PER_SQRT_MIN

    @property
    def reference(self) -> str:
        """The label the prepared quotes record: "fit" | "none"."""
        has_ref = self.reference_w is not None and bool(self.reference_forward)
        return "fit" if has_ref else "none"


@dataclass(frozen=True)
class SyncResult:
    """The synchronised slice arrays (sorted by ``k``) plus the per-quote
    diagnostics ``PreparedQuotes`` carries; ``order`` re-sorts any other array
    aligned with the input rows."""

    k: np.ndarray
    w_bid: np.ndarray
    w_mid: np.ndarray
    w_ask: np.ndarray
    order: np.ndarray
    age_min: np.ndarray
    shift_bp: np.ndarray
    widen_bp: np.ndarray
    n_synced: int


def needs_sync(quotes: Iterable[OptionQuote], snapshot: ChainSnapshot) -> bool:
    """Whether any quote carries a spot or a stamp of its own that differs
    from the chain's — False on every synchronous chain (the byte-identity
    gate: a REST chain, a stored frame, a synthetic chain)."""
    spot, ts = snapshot.spot, snapshot.timestamp
    for q in quotes:
        if q.spot is not None and q.spot != spot:
            return True
        if q.timestamp is not None and ts is not None and q.timestamp != ts:
            return True
    return False


def layers_digest(quotes: Iterable[OptionQuote]) -> str:
    """Content digest of the per-quote (strike, side, spot, stamp) layers —
    the part of a chain the data version does not see, folded into the
    prepared-quotes cache key while a slice is asynchronous."""
    h = hashlib.blake2b(digest_size=8)
    for q in quotes:
        h.update(f"{q.strike}|{q.call_put}|{q.spot}|{q.timestamp};".encode())
    return h.hexdigest()


def quote_age_minutes(quote: OptionQuote, t_now: datetime | None) -> float:
    """age_i in minutes (step 5): the chain's stamp minus the quote's, floored
    at 0; a quote without a stamp (or a chain without one) is current."""
    if quote.timestamp is None or t_now is None:
        return 0.0
    return max((t_now - quote.timestamp).total_seconds() / 60.0, 0.0)


def row_forwards(
    ctx: SyncContext, spots: np.ndarray, spot_now: float, f_now: float
) -> np.ndarray:
    """F_i per row (step 1): the chain's forward where the quote's spot IS the
    chain's (exactly — no rule applied), else ``forward_at`` once per distinct
    spot."""
    out = np.full(spots.shape, float(f_now), dtype=float)
    for s in np.unique(spots):
        if s != spot_now:
            out[spots == s] = float(ctx.forward_at(float(s)))
    return out


def grouped_early_exercise_premiums(
    eep_fn: Callable,
    spots: np.ndarray,
    f_rows: np.ndarray,
    is_call: np.ndarray,
    strikes: np.ndarray,
    k: np.ndarray,
    mids: np.ndarray,
    d: float,
    t: float,
    cash_dividends,
) -> tuple[np.ndarray, int]:
    """Step 2's de-Am, per distinct spot: ``eep_fn`` is
    ``quotes._early_exercise_premiums`` (scalar spot / forward), called once per
    group at that group's (S_i, F_i). One group ⇒ the single historical call on
    the whole arrays (byte-identical). The cash schedule is the chain's: its
    amounts are scaled to the chain's forward, a second-order effect on the
    EEP of a sub-percent spot move."""
    groups = np.unique(spots)
    if groups.size == 1:
        return eep_fn(float(groups[0]), is_call, strikes, k, mids, float(f_rows[0]), d, t, cash_dividends)
    eep = np.zeros_like(mids)
    n_ok = 0
    for s in groups:
        g = spots == s
        e, m = eep_fn(
            float(s), is_call[g], strikes[g], k[g], mids[g], float(f_rows[g][0]), d, t, cash_dividends
        )
        eep[g] = e
        n_ok += m
    return eep, n_ok


def regime_shift(
    ctx: SyncContext, k_i: np.ndarray, f_i: np.ndarray, f_now: float
) -> tuple[np.ndarray, np.ndarray]:
    """(Δw_i, k_sync) per row — step 3.

    δ_i = ln(F_now / F_i) relabels the strike, k_sync = k_i − δ_i. With a
    reference smile, Δw_i = [w0 transported from F_cal to F_now](k_sync) −
    [w0 transported from F_cal to F_i](k_i) — both through ``transported_w``
    (the SSR-linear w0(k + R h) or the exact-LV ℓ_T map), which for the
    linear regimes is exactly w0(x + (R − 1) δ_i) − w0(x), x = k_i + R h_i —
    identically 0 under sticky-strike (R = 1), returned as exact zeros rather
    than the rounding residue of two evaluations. Without a reference Δw = 0."""
    k_i = np.asarray(k_i, dtype=float)
    f_i = np.asarray(f_i, dtype=float)
    delta = np.log(float(f_now) / f_i)
    k_sync = k_i - delta
    dw = np.zeros_like(k_i)
    if ctx.reference_w is None or not ctx.reference_forward or ctx.reference_forward <= 0.0:
        return dw, k_sync
    if not is_exact_lv(ctx.regime) and ssr_of_regime(ctx.regime) == 1.0:
        return dw, k_sync  # sticky-strike: the vol at a fixed strike is what was quoted
    f_cal = float(ctx.reference_forward)
    h_now = math.log(float(f_now) / f_cal)
    for f in np.unique(f_i[delta != 0.0]):
        g = f_i == f
        h_i = math.log(float(f) / f_cal)
        w_now = transported_w(ctx.reference_w, k_sync[g], h_now, ctx.regime)
        w_then = transported_w(ctx.reference_w, k_i[g], h_i, ctx.regime)
        dw[g] = w_now - w_then
    return dw, k_sync


def age_widening(ctx: SyncContext, age_min: np.ndarray, sigma_atm: float) -> np.ndarray:
    """s_i in VOL units (step 5): a · √age_i · (σ_atm / 0.15), σ_atm the
    reference fit's ATM vol when there is one, else the chain's own."""
    a = float(ctx.age_bp_per_sqrt_min) * 1e-4
    sigma = ctx.sigma_atm if ctx.sigma_atm else sigma_atm
    scale = max(float(sigma), 0.0) / AGE_SIGMA_REF
    return a * np.sqrt(np.maximum(np.asarray(age_min, dtype=float), 0.0)) * scale


def age_weight_multiplier(
    s_iv: np.ndarray, iv_bid: np.ndarray, iv_ask: np.ndarray
) -> np.ndarray:
    """Mid-mode weight factor 1 / (1 + (s_i / s_half,i)²), s_half,i the
    half-spread in IV floored at ``HALF_SPREAD_FLOOR``: a quote whose age
    uncertainty matches its own half-spread counts half."""
    half = np.maximum(0.5 * (np.asarray(iv_ask, dtype=float) - np.asarray(iv_bid, dtype=float)), HALF_SPREAD_FLOOR)
    ratio = np.asarray(s_iv, dtype=float) / half
    return 1.0 / (1.0 + ratio * ratio)


def widen_band_by_age(band, widen_bp: np.ndarray | None, keep: np.ndarray):
    """Band-mode age widening (step 5) of a ``calib.band.BandTarget``: each
    side moved s_i further from mid (the lower edge floored at 0), ``keep``
    the edit mask aligning ``widen_bp`` (full prepared index space) with the
    band's rows. No-op — the same object — without sync diagnostics or at
    a = 0 (byte-identical)."""
    if band is None or widen_bp is None or not np.any(widen_bp > 0.0):
        return band
    s_iv = np.asarray(widen_bp, dtype=float)[keep] * 1e-4
    return type(band)(
        iv_lo=np.maximum(band.iv_lo - s_iv, 0.0), iv_mid=band.iv_mid, iv_hi=band.iv_hi + s_iv
    )


def keep_mask(n: int, edits: dict) -> np.ndarray:
    """The row mask ``quotes.apply_edits`` keeps (excluded quotes out, stale
    indices beyond the array ignored) — so the age weights align with it."""
    keep = np.ones(int(n), dtype=bool)
    for index, edit in edits.items():
        if index < n and edit.excluded:
            keep[index] = False
    return keep


def apply_age_weights(prepared, edits: dict, fit_mode: str, weights: np.ndarray | None):
    """Mid-mode age down-weighting (step 5) of a ``PreparedQuotes`` slice: the
    resolved scheme weights (aligned with ``apply_edits``' kept rows; None =
    unit) times each quote's 1 / (1 + (s_i / s_half,i)²), then re-normalized
    to mean 1 so the data-vs-regularization balance the weight schemes are
    tuned against is kept — the factor ranks stale quotes below fresh ones, it
    does not shrink the whole slice's vote. Band modes widen the band instead
    (``widen_band_by_age``); an unsynchronised slice, a = 0 or a band mode
    returns ``weights`` untouched (byte-identical)."""
    s_bp = prepared.age_widen_bp
    if fit_mode != "mid" or s_bp is None or not np.any(s_bp > 0.0):
        return weights
    mult = age_weight_multiplier(s_bp * 1e-4, prepared.iv_bid, prepared.iv_ask)
    mult = mult[keep_mask(prepared.k.size, edits)]
    out = mult if weights is None else np.asarray(weights, dtype=float) * mult
    mean = float(out.mean()) if out.size else 0.0
    return out / mean if mean > 0.0 else weights


def synchronise(
    ctx: SyncContext,
    k_i: np.ndarray,
    f_i: np.ndarray,
    f_now: float,
    w_bid: np.ndarray,
    w_mid: np.ndarray,
    w_ask: np.ndarray,
    age_min: np.ndarray,
    tau: float,
    w_atm: float,
) -> SyncResult:
    """Steps 3–5 on the kept, inverted rows: shift bid / mid / ask by the same
    Δw_i (floored at W_MIN), relabel at k_sync, re-sort by it (a stable sort —
    two layers' strikes can interleave after the relabel) and compute the
    per-quote diagnostics: the applied ΔIV at mid in vol bp, the age widening
    s_i in vol bp, and how many quotes were actually moved or aged."""
    dw, k_sync = regime_shift(ctx, k_i, f_i, f_now)
    w_bid1 = np.maximum(w_bid + dw, W_MIN)
    w_mid1 = np.maximum(w_mid + dw, W_MIN)
    w_ask1 = np.maximum(w_ask + dw, W_MIN)
    shift_bp = (np.sqrt(w_mid1 / tau) - np.sqrt(np.maximum(w_mid, W_MIN) / tau)) * 1e4
    sigma_atm = math.sqrt(max(float(w_atm), W_MIN) / tau)
    widen_bp = age_widening(ctx, age_min, sigma_atm) * 1e4
    moved = (np.asarray(f_i, dtype=float) != float(f_now)) | (np.asarray(age_min, dtype=float) > 0.0)
    order = np.argsort(k_sync, kind="stable")
    return SyncResult(
        k=k_sync[order],
        w_bid=w_bid1[order],
        w_mid=w_mid1[order],
        w_ask=w_ask1[order],
        order=order,
        age_min=np.asarray(age_min, dtype=float)[order],
        shift_bp=shift_bp[order],
        widen_bp=widen_bp[order],
        n_synced=int(np.count_nonzero(moved)),
    )
