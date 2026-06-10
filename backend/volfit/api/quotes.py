"""Chain snapshot -> slice-calibration inputs (ROADMAP Phase 5 quote prep).

For one (ticker, expiry) with parity-implied forward F and discount D
(volfit.data.forwards), each quoted strike K maps to log-moneyness
k = ln(K / F), keeping only the OTM side (call for K >= F, put below):
the OTM option carries the vega and the tight relative spread. Option
prices p are normalized to undiscounted forward units, puts converted to
calls by parity in those units (conventions of volfit.core.black),

    c = p / (D F)              (calls)
    c = p / (D F) + 1 - e^k    (puts),

then inverted strike by strike to total implied variance. The map is
monotone, so bid <= mid <= ask survives into implied-vol space. Strikes
whose bid, mid or ask violates the static bounds (1-e^k)^+ < c < 1 are
dropped entirely — a one-sided band cannot be displayed or weighted.

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

from volfit.core.black import implied_total_variance
from volfit.data.forwards import ImpliedForward
from volfit.data.types import ChainSnapshot

#: IV spread floor: protects the inverse-variance weights from locked quotes.
SPREAD_FLOOR = 1e-4

#: Wing cutoff in ATM standard deviations: quotes beyond this carry no vega
#: (at 1M a 5 sd strike has vega ~1e-6 — its implied vol is pure noise; 4 sd
#: matches the realistically quoted range and keeps every slice < 30 vol bp).
Z_MAX = 4.0

#: Initial haircut implementation: shrink the bid-ask band by this factor
#: before weighting (a stand-in until per-quote liquidity haircuts exist).
HAIRCUT_SHRINK = 0.5


@dataclass(frozen=True)
class PreparedQuotes:
    """Fit inputs and display bands for one (ticker, expiry) slice.

    Arrays are aligned and sorted by k; only strikes with a full finite
    (bid, mid, ask) implied-vol band are kept.
    """

    t: float
    forward: float
    discount: float
    k: np.ndarray
    w_mid: np.ndarray  # total variance at mid, the calibration target
    iv_bid: np.ndarray
    iv_mid: np.ndarray
    iv_ask: np.ndarray


def prepare_quotes(
    snapshot: ChainSnapshot,
    expiry: date,
    forward: ImpliedForward,
    t: float,
) -> PreparedQuotes:
    """Turn one expiry of a chain into sorted (k, w, IV-band) fit inputs."""
    f, d = forward.forward, forward.discount
    scale = 1.0 / (d * f)

    rows: list[tuple[float, float, float, float]] = []
    for quote in snapshot.quotes_for(expiry):
        if quote.bid is None or quote.ask is None or quote.mid is None:
            continue
        if quote.call_put != ("C" if quote.strike >= f else "P"):
            continue  # keep the OTM side only
        k = float(np.log(quote.strike / f))
        shift = 0.0 if quote.call_put == "C" else 1.0 - float(np.exp(k))
        rows.append(
            (k, quote.bid * scale + shift, quote.mid * scale + shift, quote.ask * scale + shift)
        )

    rows.sort(key=lambda r: r[0])
    k_arr, c_bid, c_mid, c_ask = (np.array(col) for col in zip(*rows))

    w_bid = implied_total_variance(k_arr, c_bid)
    w_mid = implied_total_variance(k_arr, c_mid)
    w_ask = implied_total_variance(k_arr, c_ask)

    keep = np.isfinite(w_bid) & np.isfinite(w_mid) & np.isfinite(w_ask)
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
    )


def fit_weights(prepared: PreparedQuotes, fit_mode: str) -> np.ndarray | None:
    """Per-quote calibration weights for the requested fit mode.

    - "mid":     unit weights (None — calibrate_slice's default);
    - "bidask":  inverse-variance in the quoted IV spread, mean-normalized
                 so penalty coefficients keep their scale across modes;
    - "haircut": same inverse-variance rule on a band shrunk by
                 HAIRCUT_SHRINK (initial haircut implementation: the floor
                 binds earlier on tight quotes, flattening ATM weights).
    """
    if fit_mode == "mid":
        return None
    spread = prepared.iv_ask - prepared.iv_bid
    if fit_mode == "haircut":
        spread = HAIRCUT_SHRINK * spread
    weights = 1.0 / np.maximum(spread, SPREAD_FLOOR) ** 2
    return weights / weights.mean()
