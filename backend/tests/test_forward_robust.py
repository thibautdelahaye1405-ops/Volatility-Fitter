"""Robust parity forward on noisy/stale live data ([REQ 2026-06-25]).

The parity SLOPE is the discount — the worst-identified parameter — and on a noisy
delayed feed (wide/stale deep-ITM quotes) the equal-weight regression drifts to an
implied discount > 1 (a negative rate), tilting the forward and gapping the smile at
the money. When a reference date is supplied (the fitting path), ``implied_forward``
clamps the discount to a physical rate band and re-derives the forward from the
well-identified level. These tests pin: (1) a clean chain is unchanged/recovered to
truth; (2) stale wings that break the unclamped fit stay sane once clamped;
(3) zero-spread close-like data still resolves; (4) no reference date = legacy.
"""

from datetime import date, datetime

import numpy as np

from volfit.core.black import black_call
from volfit.data.forwards import RATE_MAX, RATE_MIN, implied_forward
from volfit.data.types import ChainSnapshot, OptionQuote

SPOT, RATE, DIV, VOL = 100.0, 0.045, 0.01, 0.20
REF, EXPIRY = date(2026, 6, 10), date(2026, 7, 10)  # ~30d, the short-dated case that broke
T = (EXPIRY - REF).days / 365.0
F_TRUE = SPOT * np.exp((RATE - DIV) * T)
D_TRUE = np.exp(-RATE * T)


def _chain(corrupt: bool = False, zero_spread: bool = False) -> ChainSnapshot:
    """Exact European parity prices at a flat vol; optionally make the ITM calls
    stale (mid biased ABOVE true and wide-spread, growing with depth — the real
    `mid > last` pattern that tilts the parity slope), or quote everything
    zero-spread (close-like)."""
    quotes: list[OptionQuote] = []
    for strike in np.arange(60.0, 141.0, 5.0):
        k = float(np.log(strike / F_TRUE))
        call = float(D_TRUE * F_TRUE * black_call(k, VOL**2 * T))
        put = call - float(D_TRUE * (F_TRUE - strike))
        cmid, ch, ph = call, 0.01 * call, 0.01 * put  # 1% half-spread
        if corrupt and strike < SPOT:  # ITM calls: stale (over-priced) + wide, deeper = worse
            depth = (SPOT - strike) / SPOT
            cmid, ch = call * (1.0 + 0.12 * depth), 0.10 * call
        if zero_spread:
            ch = ph = 0.0
        quotes.append(OptionQuote("X", EXPIRY, float(strike), "C", bid=cmid - ch, ask=cmid + ch))
        quotes.append(OptionQuote("X", EXPIRY, float(strike), "P", bid=put - ph, ask=put + ph))
    return ChainSnapshot("X", SPOT, datetime(2026, 6, 10), quotes, "european")


def test_clean_chain_recovered_to_truth_and_unclamped():
    """On a clean chain the discount sits inside the rate band, so the clamp never
    bites and forward + discount land on truth."""
    f = implied_forward(_chain(), EXPIRY, REF)
    assert f is not None
    assert abs(f.forward / F_TRUE - 1.0) < 1e-3
    assert abs(f.discount / D_TRUE - 1.0) < 1e-3
    assert RATE_MIN <= -np.log(f.discount) / T <= RATE_MAX  # in band -> untouched


def test_stale_wings_break_unclamped_but_clamp_stays_sane():
    """Stale ITM calls tilt the slope: the unclamped fit (no reference date) returns a
    nonsensical discount (> 1, a negative rate); supplying the reference date clamps it
    to a physical rate and re-derives the forward near truth."""
    chain = _chain(corrupt=True)
    unclamped = implied_forward(chain, EXPIRY)  # no reference date -> no clamp
    clamped = implied_forward(chain, EXPIRY, REF)
    assert unclamped is not None and clamped is not None
    # the unclamped fit is broken by the stale wings (discount implies a wild rate)...
    assert unclamped.discount > 1.0 or not (RATE_MIN <= -np.log(unclamped.discount) / T <= RATE_MAX)
    # ...while the clamped discount is physically sane and the forward is near truth.
    assert RATE_MIN <= -np.log(clamped.discount) / T <= RATE_MAX
    assert abs(clamped.forward / F_TRUE - 1.0) < 0.01
    assert abs(clamped.forward / F_TRUE - 1.0) < abs(unclamped.forward / F_TRUE - 1.0)


def test_zero_spread_close_like_data_still_resolves_sane():
    """Close-like data (bid == ask, no spread signal): the clamp + ATM-kernel forward
    re-derivation still yields a sane discount + forward, not the > 1 garbage."""
    f = implied_forward(_chain(corrupt=True, zero_spread=True), EXPIRY, REF)
    assert f is not None
    assert RATE_MIN <= -np.log(f.discount) / T <= RATE_MAX
    assert abs(f.forward / F_TRUE - 1.0) < 0.01


def test_no_reference_date_skips_clamp():
    """Without a reference date the legacy regression is used unchanged (clean chain
    recovers truth; the clamp simply never runs)."""
    legacy = implied_forward(_chain(), EXPIRY)
    assert legacy is not None
    assert abs(legacy.forward / F_TRUE - 1.0) < 1e-3


def _zero_carry_chain() -> ChainSnapshot:
    """An IV-synthesized chain the way the delayed-tier fallback builds one:
    prices carry the PROVIDER's carry (call/put IVs disagree once re-priced at
    zero carry), quoted zero-spread and flagged zero_carry ([REQ 2026-07-08])."""
    base = _chain(zero_spread=True)  # true-carry parity prices, bid == ask
    return ChainSnapshot(
        base.ticker, base.spot, base.timestamp, base.quotes,
        base.exercise_style, zero_carry=True,
    )


def test_zero_carry_chain_pins_forward_to_spot():
    """A flagged zero-carry synthesized chain gets its own construction
    convention back — F = spot, D = 1, rms 0 — never a parity regression
    (which reads the provider's call/put IV asymmetry as a fake forward:
    the live SPY -3.8%-rate / +1.7%-forward incident)."""
    f = implied_forward(_zero_carry_chain(), EXPIRY, REF)
    assert f is not None
    assert f.forward == SPOT and f.discount == 1.0
    assert f.residual_rms == 0.0 and f.n_strikes > 0
    # The no-reference path pins identically (the flag, not the clamp, decides).
    g = implied_forward(_zero_carry_chain(), EXPIRY)
    assert g is not None and g.forward == SPOT and g.discount == 1.0


def test_unflagged_zero_spread_chain_still_regresses():
    """Chain-wide zero spreads alone must NOT trigger the pin: EOD close marks
    also quote bid == ask yet their mids carry genuine parity information. The
    regression result (true carry) is measurably different from the pin."""
    f = implied_forward(_chain(zero_spread=True), EXPIRY, REF)
    assert f is not None
    assert abs(f.forward / F_TRUE - 1.0) < 1e-3  # regression recovers TRUE carry
    assert f.forward != SPOT and f.discount != 1.0  # the pin did not fire

# ---------------------------------------------------------------- same-day (0DTE)

def _same_day_chain(discount: float, with_settlement: bool) -> ChainSnapshot:
    """A same-day (0DTE) chain whose parity slope carries ``discount`` exactly:
    c - p = discount * (F - K) with F = SPOT — noisy-slope 0DTE data in
    miniature. Optionally stamped with the schema-v7 settlement map."""
    from volfit.data.expiry_time import settlement_map

    expiry = date(2026, 7, 10)  # a Friday NYSE session
    ts = datetime(2026, 7, 10, 16, 30)  # 12:30 ET, 3.5h to the 16:00 settle
    quotes = []
    for strike in np.arange(95.0, 106.0, 2.5):
        put = 10.0
        call = put + discount * (SPOT - float(strike))
        quotes.append(OptionQuote("X", expiry, float(strike), "C", bid=call - 0.05, ask=call + 0.05, timestamp=ts))
        quotes.append(OptionQuote("X", expiry, float(strike), "P", bid=put - 0.05, ask=put + 0.05, timestamp=ts))
    return ChainSnapshot(
        "X", SPOT, ts, quotes, "european",
        settlement=settlement_map({expiry}, root="X") if with_settlement else None,
    )


def test_same_day_noisy_discount_clamped_over_subday_horizon():
    """A same-day expiry used to SKIP the rate-band clamp (day-granular t = 0),
    letting an absurd discount through — observed live on captured SPY 0DTE
    (D = 1.0005 ~ -125%/yr over 3.5h). With the settlement instant on the
    snapshot the clamp now runs over the exact sub-day horizon."""
    noisy = 1.0005
    f = implied_forward(_same_day_chain(noisy, with_settlement=True), date(2026, 7, 10), date(2026, 7, 10))
    assert f is not None
    t = 3.5 / 24.0 / 365.0
    assert f.discount <= np.exp(-RATE_MIN * t) + 1e-12  # inside the physical band
    assert f.discount < noisy  # the absurd slope was actually clamped
    assert abs(f.forward / SPOT - 1.0) < 5e-3  # forward re-derived off the level


def test_same_day_without_settlement_keeps_legacy_skip():
    """Legacy rows (no settlement map) keep the historical behavior exactly:
    same-day day-granular t = 0 -> the clamp never runs."""
    noisy = 1.0005
    f = implied_forward(_same_day_chain(noisy, with_settlement=False), date(2026, 7, 10), date(2026, 7, 10))
    assert f is not None
    assert abs(f.discount - noisy) < 1e-6  # untouched


def test_future_expiry_horizon_is_day_granular_byte_identical():
    """The clamp horizon for any future expiry is the day count — the
    settlement map must not perturb it (byte-identity of existing fits)."""
    from volfit.data.forwards import _clamp_horizon

    chain = _chain()
    assert _clamp_horizon(chain, EXPIRY, REF) == T
