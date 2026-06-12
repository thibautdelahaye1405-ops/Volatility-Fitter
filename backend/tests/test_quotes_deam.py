"""Golden de-Americanization tests for quote prep (realism block, [REQ]).

No HTTP: prepare_quotes is exercised directly. An American chain generated
by the CRR tree at a known smile sigma(k) = 0.2 + 0.05 k^2 (S=100, r=5%,
q=2%, t=0.5) must come back from quote prep within tree tolerance of that
smile, and must beat the naive treatment (inverting American prices as if
European), which is biased high wherever early exercise carries value —
OTM puts under r > q here. A truly European chain must pass through the
pipeline untouched (n_deamericanized == 0, machine-precision round trip).
"""

from datetime import date, datetime, timedelta

import numpy as np
import pytest

from volfit.api.quotes import apply_edits, prepare_quotes
from volfit.api.session import QuoteEdit
from volfit.core.american import DEFAULT_BATCH_STEPS, binomial_price
from volfit.core.black import black_call
from volfit.data.forwards import ResolvedForward
from volfit.data.types import ChainSnapshot, OptionQuote

REF_DATE = date(2026, 6, 10)
EXPIRY = REF_DATE + timedelta(days=182)
TIMESTAMP = datetime(2026, 6, 10, 16, 0)

T = 0.5
SPOT = 100.0
RATE = 0.05
DIV_YIELD = 0.02
FORWARD = SPOT * float(np.exp((RATE - DIV_YIELD) * T))
DISCOUNT = float(np.exp(-RATE * T))
RESOLVED = ResolvedForward(expiry=EXPIRY, forward=FORWARD, discount=DISCOUNT, source="manual")

#: ~12 strikes spanning 0.8F .. 1.25F (all inside the Z_MAX wing filter).
MONEYNESS = np.linspace(0.80, 1.25, 12)

#: Half bid-ask spread in price units (clamped so deep-wing bids stay > 0).
HALF_SPREAD = 0.15

#: Tree/EEP approximation tolerance on recovered mids: 30 vol bp.
TOL_VOL = 30e-4


def smile_vol(k: float | np.ndarray) -> float | np.ndarray:
    """The known smile the chains are generated from."""
    return 0.2 + 0.05 * np.asarray(k) ** 2


def _quote(strike: float, cp: str, mid: float) -> OptionQuote:
    half = min(HALF_SPREAD, 0.45 * mid)
    return OptionQuote(
        ticker="X",
        expiry=EXPIRY,
        strike=strike,
        call_put=cp,
        bid=mid - half,
        ask=mid + half,
        last=mid,
        timestamp=TIMESTAMP,
    )


def make_american_chain(exercise_style: str) -> ChainSnapshot:
    """AMERICAN CRR prices at sigma(k), calls and puts at every strike (so
    the OTM side exists everywhere); the style flag decides whether quote
    prep de-Americanizes ("american") or naively inverts ("european")."""
    quotes = []
    for m in MONEYNESS:
        strike = float(m * FORWARD)
        sigma = float(smile_vol(np.log(strike / FORWARD)))
        for cp in ("C", "P"):
            mid = binomial_price(
                cp == "C", SPOT, strike, T, sigma, RATE, DIV_YIELD,
                n_steps=DEFAULT_BATCH_STEPS, american=True,
            )
            quotes.append(_quote(strike, cp, mid))
    return ChainSnapshot("X", SPOT, TIMESTAMP, quotes, exercise_style=exercise_style)


def make_european_chain() -> ChainSnapshot:
    """Exact Black European prices at sigma(k) (puts by parity)."""
    quotes = []
    for m in MONEYNESS:
        strike = float(m * FORWARD)
        k = float(np.log(strike / FORWARD))
        w = float(smile_vol(k)) ** 2 * T
        call = DISCOUNT * FORWARD * float(black_call(k, w))
        put = call - DISCOUNT * (FORWARD - strike)
        quotes.append(_quote(strike, "C", call))
        quotes.append(_quote(strike, "P", put))
    return ChainSnapshot("X", SPOT, TIMESTAMP, quotes, exercise_style="european")


# -- American golden round trip ----------------------------------------------


def test_american_round_trip_recovers_smile():
    prepared = prepare_quotes(make_american_chain("american"), EXPIRY, RESOLVED, T)
    assert prepared.n_deamericanized > 0
    assert prepared.k.size >= 10  # the ladder survives the bound/wing filters
    errors = np.abs(prepared.iv_mid - smile_vol(prepared.k))
    assert errors.max() < TOL_VOL, errors


def test_american_prep_beats_naive_european_inversion():
    am = prepare_quotes(make_american_chain("american"), EXPIRY, RESOLVED, T)
    naive = prepare_quotes(make_american_chain("european"), EXPIRY, RESOLVED, T)
    assert naive.n_deamericanized == 0

    # Match shared strikes by k (the two preps may keep different subsets).
    am_err, nv_err, ks = [], [], []
    for i, k in enumerate(am.k):
        j = int(np.argmin(np.abs(naive.k - k)))
        if abs(float(naive.k[j]) - float(k)) > 1e-12:
            continue
        target = float(smile_vol(k))
        am_err.append(abs(float(am.iv_mid[i]) - target))
        nv_err.append(abs(float(naive.iv_mid[j]) - target))
        ks.append(float(k))
    am_err, nv_err, ks = np.array(am_err), np.array(nv_err), np.array(ks)
    assert ks.size >= 8

    # Early exercise bites on the put side (k < 0) under r > q: the naive
    # inversion reads the EEP as extra vol, de-Americanization strips it.
    puts = ks < 0.0
    assert puts.any()
    assert nv_err[puts].mean() > am_err[puts].mean()
    assert nv_err[puts].max() > am_err[puts].max()
    # And nowhere does de-Americanization make things materially worse.
    assert (am_err <= nv_err + 5e-4).all(), (ks, am_err, nv_err)


# -- European chains are untouched -------------------------------------------


def test_european_chain_passes_through_unchanged():
    prepared = prepare_quotes(make_european_chain(), EXPIRY, RESOLVED, T)
    assert prepared.n_deamericanized == 0
    # Symmetric spreads: mids are exact model prices, recovered to root
    # tolerance — the pre-de-Am pipeline behaviour, byte for byte.
    errors = np.abs(prepared.iv_mid - smile_vol(prepared.k))
    assert errors.max() < 1e-5, errors


# -- stale edit indices -------------------------------------------------------


def test_apply_edits_ignores_out_of_range_indices():
    prepared = prepare_quotes(make_european_chain(), EXPIRY, RESOLVED, T)
    stale = {prepared.k.size + 3: QuoteEdit(excluded=True)}
    k, w, weights = apply_edits(prepared, stale, None)  # must not raise
    assert k.size == prepared.k.size
    assert np.array_equal(w, prepared.w_mid)
    assert weights is None
