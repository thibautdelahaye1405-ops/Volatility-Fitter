"""Golden locks for the quote synchronisation (volfit.api.quote_sync).

The contracts, in the module's own order:

1. BYTE-IDENTITY — on a chain whose quotes all share the chain's spot and stamp
   (a REST chain, a stored frame) the prepared arrays, the band and the weights
   are identical with the feature on or off, European and American alike.
2. THE ERROR IT REMOVES — quotes generated from a known smile at a spot 0.1 %
   below the chain's, read naively at the chain's forward, mis-read the ATM IV
   by tens of vol bp; synchronised under sticky-strike (R = 1) they match the
   smile within 1 bp. Under R = 0 the synchronised quote equals the smile
   re-labelled in moneyness (fixed-moneyness invariance); under R = 2 the
   regime shift equals the reference slope times δ to first order.
3. AGE — the band widens by s_i per side in the band modes; the mid-mode
   weights shrink by 1 / (1 + (s_i / s_half)²) relative to fresh quotes;
   a = 0 changes nothing.
4. NO REFERENCE FIT — Δw = 0 and the slice records ``sync_reference = "none"``.
5. THE SERVICE — the context is built from the node's last committed fit, the
   cache key folds it, and the switch turns the whole step off.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from volfit.api import service
from volfit.api.quote_sync import SyncContext, apply_age_weights, regime_shift
from volfit.api.quotes import apply_band_edits, prepare_quotes
from volfit.api.session import QuoteEdit
from volfit.api.state import AppState
from volfit.core.american import DEFAULT_BATCH_STEPS, binomial_price
from volfit.core.black import black_call
from volfit.data.forwards import ImpliedForward
from volfit.data.types import ChainSnapshot, OptionQuote

EXPIRY = date(2026, 7, 10)
TS = datetime(2026, 6, 10, 20, 0)
T = 30.0 / 365.0
F_NOW = 100.0  # zero carry: F = S, D = 1
MOVE = 1e-3  # the older layer was quoted 0.1 % below the chain's spot
S_OLD = F_NOW * (1.0 - MOVE)
STRIKES = np.linspace(90.0, 110.0, 21)
SPREAD = 0.01  # relative price half-spread


def sigma_ref(k):
    """The known (skewed) smile: sigma(k) = 0.20 - 0.25 k + 0.5 k^2."""
    k = np.asarray(k, dtype=float)
    return 0.20 - 0.25 * k + 0.5 * k * k


def w_ref(k):
    return sigma_ref(k) ** 2 * T


def _fwd() -> ImpliedForward:
    return ImpliedForward(expiry=EXPIRY, forward=F_NOW, discount=1.0, n_strikes=21, residual_rms=0.0)


def _chain(spot_quoted: float, sigma_of_strike, tag_spot: bool, stamp: datetime = TS,
           stale: set[float] | None = None, stale_by: timedelta = timedelta(minutes=4)) -> ChainSnapshot:
    """A European chain PRICED at spot ``spot_quoted`` (F = S) with vol
    ``sigma_of_strike(K)``; ``tag_spot`` writes that spot on the quotes (the
    layer's own), else they read as quoted at the chain's. The CHAIN is at
    F_NOW / TS; ``stale`` strikes are stamped ``stale_by`` earlier."""
    quotes = []
    for strike in STRIKES:
        k_i = np.log(strike / spot_quoted)
        sigma = float(sigma_of_strike(strike))
        call = spot_quoted * float(black_call(k_i, sigma * sigma * T))
        put = call - (spot_quoted - strike)
        ts = stamp - stale_by if stale and strike in stale else stamp
        for cp, mid in (("C", call), ("P", put)):
            quotes.append(OptionQuote(
                ticker="X", expiry=EXPIRY, strike=float(strike), call_put=cp,
                bid=mid * (1.0 - SPREAD), ask=mid * (1.0 + SPREAD), timestamp=ts,
                spot=spot_quoted if tag_spot else None,
            ))
    return ChainSnapshot(ticker="X", spot=F_NOW, timestamp=TS, quotes=quotes)


def _ctx(regime="sticky_strike", reference: bool = True, a: float = 3.6) -> SyncContext:
    return SyncContext(
        forward_at=lambda s: F_NOW * s / F_NOW,  # proportional: F_i = F_now S_i / S_now
        regime=regime,
        reference_w=w_ref if reference else None,
        reference_forward=F_NOW if reference else None,
        sigma_atm=0.20 if reference else None,
        age_bp_per_sqrt_min=a,
    )


def _american_chain(tag: bool) -> ChainSnapshot:
    """CRR American prices at sigma(k) (S = 100, r = 5 %, q = 2 %, t = 0.5),
    calls and puts at every strike, all quoted at the chain's spot / stamp."""
    spot, r, q, t = 100.0, 0.05, 0.02, 0.5
    fwd = spot * float(np.exp((r - q) * t))
    quotes = []
    for m in np.linspace(0.85, 1.2, 9):
        strike = float(m * fwd)
        sigma = float(sigma_ref(np.log(strike / fwd)))
        for cp in ("C", "P"):
            mid = binomial_price(cp == "C", spot, strike, t, sigma, r, q,
                                 n_steps=DEFAULT_BATCH_STEPS, american=True)
            half = min(0.15, 0.45 * mid)
            quotes.append(OptionQuote(
                ticker="A", expiry=EXPIRY, strike=strike, call_put=cp, bid=mid - half, ask=mid + half,
                timestamp=TS, spot=spot if tag else None,
            ))
    snap = ChainSnapshot(ticker="A", spot=spot, timestamp=TS, quotes=quotes, exercise_style="american")
    return snap, ImpliedForward(expiry=EXPIRY, forward=fwd, discount=float(np.exp(-r * t)),
                                n_strikes=9, residual_rms=0.0), t


# ----------------------------------------------------------- 1. byte-identity

def _assert_identical(a, b) -> None:
    for name in ("k", "w_mid", "iv_bid", "iv_mid", "iv_ask"):
        assert np.array_equal(getattr(a, name), getattr(b, name)), name
    for mode in ("bidask", "haircut"):
        ba, bb = apply_band_edits(a, {}, mode), apply_band_edits(b, {}, mode)
        assert np.array_equal(ba.iv_lo, bb.iv_lo) and np.array_equal(ba.iv_hi, bb.iv_hi), mode
    assert apply_age_weights(b, {}, "mid", None) is None
    assert b.sync_reference == "none" and b.n_synced == 0 and b.age_min is None


def test_synchronous_european_chain_is_byte_identical_on_or_off():
    for tag in (False, True):  # quotes without a spot, or carrying the chain's own
        snap = _chain(F_NOW, lambda K: sigma_ref(np.log(K / F_NOW)), tag_spot=tag)
        off = prepare_quotes(snap, EXPIRY, _fwd(), T)
        on = prepare_quotes(snap, EXPIRY, _fwd(), T, sync=_ctx())
        _assert_identical(off, on)


def test_synchronous_american_chain_is_byte_identical_on_or_off():
    """The grouped de-Am collapses to the single historical call."""
    for tag in (False, True):
        snap, fwd, t = _american_chain(tag)
        off = prepare_quotes(snap, EXPIRY, fwd, t)
        on = prepare_quotes(snap, EXPIRY, fwd, t, sync=_ctx())
        _assert_identical(off, on)
        assert on.n_deamericanized == off.n_deamericanized > 0
        assert np.array_equal(on.eep, off.eep)


# ------------------------------------------------- 2. the error it removes

def _sticky_strike_layer(tag: bool) -> ChainSnapshot:
    """Quoted at S_OLD with the vol each STRIKE has on the reference smile at
    F_NOW (sticky-strike truth): the quote's IV at its strike is unchanged."""
    return _chain(S_OLD, lambda K: sigma_ref(np.log(K / F_NOW)), tag_spot=tag)


def test_naive_read_is_off_by_tens_of_bp_and_sync_recovers_the_smile_under_sticky_strike():
    naive = prepare_quotes(_sticky_strike_layer(tag=False), EXPIRY, _fwd(), T)
    err_naive = np.abs(naive.iv_mid - sigma_ref(naive.k)) * 1e4
    atm = int(np.argmin(np.abs(naive.k)))
    assert err_naive[atm] > 20.0, f"naive ATM error {err_naive[atm]:.1f} bp"  # measured ≈ 43 bp

    synced = prepare_quotes(_sticky_strike_layer(tag=True), EXPIRY, _fwd(), T, sync=_ctx("sticky_strike"))
    assert synced.sync_reference == "fit" and synced.n_synced == synced.k.size
    assert np.allclose(synced.k, np.log(STRIKES / F_NOW))  # every strike kept, relabelled at F_now
    err_sync = np.abs(synced.iv_mid - sigma_ref(synced.k)) * 1e4
    assert err_sync.max() < 1.0, f"synchronised max error {err_sync.max():.3f} bp"
    assert np.all(synced.sync_shift_bp == 0.0)  # R = 1: no regime correction
    # The band survives in w: bid < mid < ask, and the spread is the quoted one.
    assert np.all(synced.iv_bid < synced.iv_mid) and np.all(synced.iv_mid < synced.iv_ask)
    print(f"naive ATM error {err_naive[atm]:.1f} bp -> synchronised {err_sync[atm]:.4f} bp")


def test_sticky_moneyness_layer_is_relabelled_in_moneyness_under_r0():
    """Sticky-moneyness truth: the layer quotes sigma_ref at ITS moneyness.
    Under R = 0 the synchronised quote is the reference at k = ln(K / F_now)."""
    layer = _chain(S_OLD, lambda K: sigma_ref(np.log(K / S_OLD)), tag_spot=True)
    synced = prepare_quotes(layer, EXPIRY, _fwd(), T, sync=_ctx("sticky_moneyness"))
    err = np.abs(synced.iv_mid - sigma_ref(synced.k)) * 1e4
    assert err.max() < 0.05, err.max()
    assert np.any(synced.sync_shift_bp != 0.0)  # a genuine regime correction was applied
    # ... which the naive read (no spot tag) does NOT give: it mis-labels the quote.
    naive = prepare_quotes(_chain(S_OLD, lambda K: sigma_ref(np.log(K / S_OLD)), tag_spot=False),
                           EXPIRY, _fwd(), T)
    assert np.abs(naive.iv_mid - sigma_ref(naive.k)).max() * 1e4 > 20.0


def test_r2_shift_equals_reference_slope_times_delta_to_first_order():
    k_i = np.log(STRIKES / S_OLD)
    f_i = np.full(k_i.shape, S_OLD)
    dw, k_sync = regime_shift(_ctx(regime=2.0), k_i, f_i, F_NOW)
    delta = np.log(F_NOW / S_OLD)
    assert np.allclose(k_sync, np.log(STRIKES / F_NOW))
    slope = 2.0 * sigma_ref(k_i) * (-0.25 + k_i) * T  # d w_ref / dk
    assert np.allclose(dw, slope * delta, rtol=0.02)
    assert np.all(dw[k_i < 0.05] < 0.0)  # negative skew: the lower-spot read sits above


def test_no_reference_fit_means_no_regime_correction():
    synced = prepare_quotes(_sticky_strike_layer(tag=True), EXPIRY, _fwd(), T,
                            sync=_ctx("sticky_moneyness", reference=False))
    assert synced.sync_reference == "none"
    assert np.all(synced.sync_shift_bp == 0.0)
    assert np.allclose(synced.k, np.log(STRIKES / F_NOW))  # relabelled at F_now
    assert np.abs(synced.iv_mid - sigma_ref(synced.k)).max() * 1e4 < 1.0  # sticky-strike behaviour


# ---------------------------------------------------------------- 3. age

STALE = {94.0, 100.0, 106.0}


def _aged(a: float = 3.6):
    snap = _chain(F_NOW, lambda K: sigma_ref(np.log(K / F_NOW)), tag_spot=False, stale=STALE)
    return prepare_quotes(snap, EXPIRY, _fwd(), T), prepare_quotes(snap, EXPIRY, _fwd(), T, sync=_ctx(a=a))


def test_age_widens_the_band_by_s_per_side_in_band_modes():
    fresh, aged = _aged()
    assert np.array_equal(fresh.k, aged.k) and np.array_equal(fresh.iv_mid, aged.iv_mid)
    stale = np.isin(np.round(np.exp(aged.k) * F_NOW, 6), sorted(STALE))
    assert np.allclose(aged.age_min[stale], 4.0) and np.all(aged.age_min[~stale] == 0.0)
    s = 3.6e-4 * np.sqrt(4.0) * (0.20 / 0.15)  # a sqrt(age) sigma_atm / 0.15, in vol
    assert np.allclose(aged.age_widen_bp[stale], s * 1e4) and np.all(aged.age_widen_bp[~stale] == 0.0)
    for mode in ("bidask", "haircut"):
        b0, b1 = apply_band_edits(fresh, {}, mode), apply_band_edits(aged, {}, mode)
        assert np.allclose(b1.iv_hi - b0.iv_hi, np.where(stale, s, 0.0))
        assert np.allclose(b0.iv_lo - b1.iv_lo, np.where(stale, s, 0.0))
        assert np.array_equal(b0.iv_mid, b1.iv_mid)
    # The excluded-row alignment survives (the full-index band too).
    edits = {0: QuoteEdit(excluded=True)}
    b = apply_band_edits(aged, edits, "bidask")
    assert b.iv_lo.size == aged.k.size - 1
    assert apply_band_edits(aged, edits, "bidask", include_excluded=True).iv_lo.size == aged.k.size


def test_age_shrinks_mid_mode_weights_relative_to_fresh_quotes():
    fresh, aged = _aged()
    stale = aged.age_widen_bp > 0.0
    w = apply_age_weights(aged, {}, "mid", None)
    assert w is not None and w.size == aged.k.size and np.isclose(w.mean(), 1.0)
    half = np.maximum(0.5 * (aged.iv_ask - aged.iv_bid), 1e-4)
    mult = 1.0 / (1.0 + (aged.age_widen_bp * 1e-4 / half) ** 2)
    assert np.all(mult[stale] < 1.0) and np.all(mult[~stale] == 1.0)
    assert mult[stale].min() < 0.5  # the tight wing quotes: age uncertainty beyond their half-spread
    assert np.allclose(w[stale] / w[~stale][0], mult[stale] / mult[~stale][0])
    # Scheme weights are multiplied, band modes untouched, exclusions aligned.
    scheme = np.linspace(0.5, 1.5, aged.k.size)
    ws = apply_age_weights(aged, {}, "mid", scheme)
    assert np.allclose(ws / ws.mean(), (scheme * mult) / (scheme * mult).mean())
    assert apply_age_weights(aged, {}, "bidask", scheme) is scheme
    assert apply_age_weights(aged, {0: QuoteEdit(excluded=True)}, "mid", None).size == aged.k.size - 1
    assert apply_age_weights(fresh, {}, "mid", None) is None


def test_zero_age_coefficient_changes_nothing():
    fresh, aged = _aged(a=0.0)
    assert np.all(aged.age_widen_bp == 0.0) and np.allclose(aged.age_min.max(), 4.0)
    for mode in ("bidask", "haircut"):
        b0, b1 = apply_band_edits(fresh, {}, mode), apply_band_edits(aged, {}, mode)
        assert np.array_equal(b0.iv_lo, b1.iv_lo) and np.array_equal(b0.iv_hi, b1.iv_hi)
    assert apply_age_weights(aged, {}, "mid", None) is None


# ------------------------------------------------------------- 5. service

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _asynchronous_state() -> tuple[AppState, date]:
    """A synthetic state with a COMMITTED fit on one node, then that node's
    chain re-installed with half its quotes tagged as an older layer (spot
    0.1 % lower, stamped 2 min earlier)."""
    state = AppState(REF_DATE)
    expiry = sorted(state.forwards(TICKER))[1]
    service.calibrate_node(state, TICKER, expiry.isoformat(), "mid")
    snap = state.snapshot(TICKER)
    older = snap.timestamp - timedelta(minutes=2)
    quotes = [
        replace(q, spot=snap.spot * (1.0 - MOVE), timestamp=older)
        if q.expiry == expiry and i % 2 == 0 else q
        for i, q in enumerate(snap.quotes)
    ]
    with state._lock:
        state._snapshots[TICKER] = replace(snap, quotes=quotes)
    state.bump_data_version(TICKER)
    return state, expiry


def test_service_builds_the_context_from_the_last_committed_fit_and_keys_the_cache():
    state, expiry = _asynchronous_state()
    forward = state.resolved_forward(TICKER, expiry)
    ctx, key = service.sync_context(state, TICKER, expiry, forward, state.year_fraction(expiry))
    assert ctx is not None and ctx.reference == "fit" and ctx.sigma_atm > 0.0
    assert key is not None and key[2] is not None  # the reference fit's digest
    assert ctx.forward_at(state.snapshot(TICKER).spot) == pytest.approx(forward.forward)
    prepared = service.prepared_quotes(state, TICKER, expiry)
    assert prepared.sync_reference == "fit" and prepared.n_synced > 0
    assert prepared.age_min.max() == pytest.approx(2.0)
    assert np.all(np.isfinite(prepared.iv_mid))
    # A synchronous node (the other expiry) keys and prepares exactly as before.
    other = sorted(state.forwards(TICKER))[2]
    assert service.sync_context(state, TICKER, other, state.resolved_forward(TICKER, other), 0.5) == (None, None)
    assert service.prepared_quotes(state, TICKER, other).sync_reference == "none"


def test_service_switch_turns_the_step_off_and_bumps_the_options_version():
    state, expiry = _asynchronous_state()
    v0 = state.options_version
    state.set_options(state.options().model_copy(update={"quoteSync": False}))
    assert state.options_version == v0 + 1
    forward = state.resolved_forward(TICKER, expiry)
    assert service.sync_context(state, TICKER, expiry, forward, state.year_fraction(expiry)) == (None, None)
    off = service.prepared_quotes(state, TICKER, expiry)
    assert off.sync_reference == "none" and off.n_synced == 0 and off.age_min is None
    naive = prepare_quotes(state.snapshot(TICKER), expiry, forward, state.year_fraction(expiry),
                           state.cash_dividend_schedule(TICKER, expiry, forward.forward))
    assert np.array_equal(off.k, naive.k) and np.array_equal(off.w_mid, naive.w_mid)
    state.set_options(state.options().model_copy(update={"quoteSync": True, "quoteSyncAgeBpPerSqrtMin": 5.0}))
    assert state.options_version == v0 + 2
    on = service.prepared_quotes(state, TICKER, expiry)
    assert on.sync_reference == "fit" and not np.array_equal(on.k, naive.k)
