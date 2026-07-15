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

Tick-noise floor: on chains from real market feeds (``ChainSnapshot.tick_size``
set), OTM quotes priced at or below ``TICK_FLOOR_TICKS`` ticks are dropped
before anything else — their price quantum, not the market, sets the implied
vol (see the constant's note for the SPY weekly staircase this cures). Exact-
price chains (synthetic, IV-synthesized) carry no tick size and skip it.

Wing filter (the Phase-3 "outlier filter" item): quotes further than
Z_MAX standard deviations from the forward, |k| > Z_MAX * sqrt(w_atm),
are excluded. Such options carry essentially no vega, so their implied
vols are numerically meaningless and would dominate max-IV-error
diagnostics without informing the fit (the synthetic 1M chain quotes
strikes out to ~6.5 sd, exactly this failure mode).

Pre-de-Am screen (speed note Stage 3): de-Americanization is the cost on this
path, yet on a wide American chain many rows are de-Amed only to be dropped
later by the static-bound / wing filters. ``_pre_deam_screen`` removes, BEFORE
the CRR trees run, only rows those later filters are guaranteed to drop anyway
(a non-positive bid, which de-Am can only lower further; and far-wing strikes
beyond a buffered Z_MAX cut). It is output-preserving by construction — the
prepared (k, w, IV) arrays are byte-identical with the screen on or off — so it
trades no quote quality for fewer tree pricings. Pass ``prefilter=False`` to
disable it (used by the equivalence tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from volfit.api.session import QuoteEdit
from volfit.calib.band import DEFAULT_HAIRCUT, BandTarget, resolve_band
from volfit.calib.convex_deam import convex_wing_repair
from volfit.core.american import deamericanize_batch
from volfit.core.black import black_call, black_vega_sigma, implied_total_variance
from volfit.data.forwards import ImpliedForward, ResolvedForward
from volfit.data.types import ChainSnapshot

#: Wing cutoff in ATM standard deviations: quotes beyond this carry no vega
#: (at 1M a 5 sd strike has vega ~1e-6 — its implied vol is pure noise; 4 sd
#: matches the realistically quoted range and keeps every slice < 30 vol bp).
Z_MAX = 4.0

#: Pre-de-Am wing buffer (Stage 3). Rows beyond ``PREFILTER_WING_BUFFER * Z_MAX``
#: ATM standard deviations are guaranteed to fail the final Z_MAX wing filter:
#: de-Am only lowers wing variance and barely moves ATM, and the ATM variance
#: estimated from the raw American mids is >= the de-Amed one, so the buffered
#: cut is strictly looser than the final cut. 1.5 leaves generous margin.
PREFILTER_WING_BUFFER = 1.5

#: Tick-noise price floor, in ticks of the snapshot's venue increment: OTM
#: quotes whose BID is at or below this many ticks are dropped — a price known
#: only to ±half a tick out of ≤3 ticks carries no implied-vol information.
#: The failure mode it removes is vivid on short-dated wings priced off a
#: stale/delayed feed: SPY 1-week calls quoted flat at $0.02 across 14 strikes
#: invert to an IV "ramp" from 11% to 15% with a gap down at every one-tick
#: step, and the smile fit chases that staircase. The Z_MAX moneyness filter
#: cannot catch these — on a steep weekly they sit well inside 4 sd.
#:
#: Measured on the bid — the side the market COMMITS to — not the mid
#: (2026-07-15, was mid-based): since bid <= mid the bid test subsumes the
#: old one, and it closes the hole the 0DTE campaign found: a wing strike
#: quoted 0.01 x 0.07 (QQQ 10-16 DTE K=835, neighbors asking 0.02-0.03) or
#: 0.02 x 0.06 carries a mid of 4-5 ticks purely on the strength of a junk
#: ask, and its "IV" sits vol points above the wing while the fit agrees
#: with every neighboring ask. Only chains from real market feeds carry a
#: ``tick_size`` (see ChainSnapshot); synthetic / IV-exact chains have no
#: price quantum and skip the floor, so every exact-price pipeline stays
#: byte-identical.
TICK_FLOOR_TICKS = 3.0

#: Explicit intrinsic tolerance (normalized-call price units) for the
#: quarantine CLASSIFICATION: a side at or below intrinsic + this tolerance
#: is reported as "below_intrinsic" rather than a generic inversion failure.
#: 0.0 matches implied_total_variance's strict lower bound exactly, so the
#: kept/dropped quote sets are byte-identical to the pre-quarantine pipeline
#: (roadmap R1 item 6: name the drop, don't change it — yet).
INTRINSIC_TOL = 0.0

#: Per-quote vega-floor diagnostic threshold (vol-units Black vega): kept
#: quotes below it are counted on the prepared slice — where the count is
#: material, IV-space residuals are numerically meaningless and the price-
#: space objectives (LQD / affine LV already fit vega-normalized price)
#: are the authoritative view. Mirrors the affine _VEGA_FLOOR.
VEGA_FLOOR_DIAG = 1e-3


@dataclass(frozen=True)
class ScreenedQuote:
    """One quote the preparation quarantined, with the REASON it was dropped.

    The screens themselves predate this record (tick floor, static bounds,
    wing cut, ...) but used to drop silently; a desk auditing a thin weekly
    needs to see WHY a strike is absent (roadmap R1 item 6). Reasons:
    ``missing_or_crossed`` (no two-sided market), ``tick_floor`` (price at a
    few ticks — the quantum, not the market, sets the IV),
    ``nonpositive_bid`` (bid <= 0 after screens: unclearable lower bound),
    ``below_intrinsic`` (a side at or below intrinsic value — near-zero time
    value, no stable IV exists), ``price_bound`` (a side at or above the
    upper static bound), ``iv_unresolvable`` (inside the bounds but the
    inversion failed), ``wing`` (beyond Z_MAX ATM standard deviations).
    """

    strike: float
    call_put: str  # "C" | "P"
    k: float  # log-moneyness ln(K/F)
    reason: str


@dataclass(frozen=True)
class PreparedQuotes:
    """Fit inputs and display bands for one (ticker, expiry) slice.

    Arrays are aligned and sorted by k; only strikes with a full finite
    (bid, mid, ask) implied-vol band are kept. `n_deamericanized` counts the
    quotes whose early-exercise premium was stripped before inversion
    (always 0 for European snapshots).
    """

    t: float  # CALENDAR year fraction (maturity axis, discounting, de-Am, carry)
    forward: float
    discount: float
    k: np.ndarray
    w_mid: np.ndarray  # total variance at mid (price-derived, clock-independent)
    iv_bid: np.ndarray
    iv_mid: np.ndarray
    iv_ask: np.ndarray
    n_deamericanized: int = 0
    #: Rows actually fed to the de-Am trees after the Stage-3 pre-screen (equals
    #: the OTM-row count when the screen removes nothing or is disabled). Pure
    #: diagnostic — lets a test confirm the screen cut tree work on wide chains.
    n_deam_input: int = 0
    #: Event-WEIGHTED variance years (volfit.calib.weighted_time). The smile is
    #: fit / quoted in this clock, so iv = sqrt(w / tau): adding an event before
    #: the expiry raises tau and lowers every reported vol at fixed price.
    #: Defaults to ``t`` (no events) so the calendar pipeline is byte-identical.
    tau: float = 0.0
    #: Quotes the preparation quarantined, each with its reason (R1 item 6) —
    #: pure observability: the kept set is unchanged, the drops are named.
    screened: tuple[ScreenedQuote, ...] = ()
    #: Per-quote early-exercise premium stripped before inversion, aligned
    #: with ``k`` (None on European chains). Where EEP is a large fraction of
    #: the mid, the de-Am MODEL — not the market — dominates the quote's IV.
    eep: np.ndarray | None = None
    #: Kept quotes whose Black vega (vol units, the fit clock) sits below
    #: VEGA_FLOOR_DIAG: their IV residuals are numerically meaningless and
    #: price-space objectives are the honest view (roadmap R1 item 6).
    vega_floored: int = 0

    def __post_init__(self) -> None:
        if self.tau <= 0.0:
            object.__setattr__(self, "tau", self.t)


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


def _pre_deam_screen(
    k: np.ndarray,
    bid: np.ndarray,
    mid: np.ndarray,
    is_call: np.ndarray,
    scale: float,
) -> np.ndarray:
    """(keep, bid_ok) masks of rows worth de-Americanizing (module doc, Stage 3).

    ``bid_ok`` is returned separately so the caller can NAME each drop:
    rows failing it quarantine as ``nonpositive_bid``, rows passing it but
    failing the buffered wing cut quarantine as ``wing``.

    Two output-preserving screens, both provably subsets of the existing
    post-de-Am filters, so the prepared arrays stay byte-identical:

    - ``bid <= 0`` (or non-finite): de-Am only lowers the bid, so the row can
      never clear the strict lower static bound — it is always dropped later.
    - ``|k|`` beyond ``PREFILTER_WING_BUFFER * Z_MAX * sqrt(w_atm)``: the final
      wing filter cuts at ``Z_MAX * sqrt(w_atm_final)``; the ATM variance here is
      estimated from the raw (American) mids, which read >= the de-Amed variance,
      so the buffered cut is strictly looser and removes only rows the final cut
      would also remove.

    The ATM estimate inverts the raw mids as if European (cheap, no tree); at
    ATM the early-exercise premium is ~0 so it is accurate, and where it is
    unusable (no two finite near-ATM mids) the wing screen is skipped.
    """
    bid_ok = np.isfinite(bid) & (bid > 0.0)
    keep = bid_ok.copy()
    shift = np.where(is_call, 0.0, 1.0 - np.exp(k))
    w_raw = implied_total_variance(k, mid * scale + shift)
    finite = np.isfinite(w_raw)
    if int(finite.sum()) >= 2:
        w_atm = float(np.interp(0.0, k[finite], w_raw[finite]))
        if np.isfinite(w_atm) and w_atm > 0.0:
            keep &= np.abs(k) <= PREFILTER_WING_BUFFER * Z_MAX * np.sqrt(w_atm)
    return keep, bid_ok


def prepare_quotes(
    snapshot: ChainSnapshot,
    expiry: date,
    forward: ResolvedForward | ImpliedForward,
    t: float,
    cash_dividends: tuple[np.ndarray, np.ndarray, float] | None = None,
    tau: float | None = None,
    prefilter: bool = True,
    convex_deam: bool = True,
) -> PreparedQuotes:
    """Turn one expiry of a chain into sorted (k, w, IV-band) fit inputs.

    ``cash_dividends`` (ex-times, scaled amounts, rate) routes American de-
    Americanization through a discrete escrowed CASH schedule (volfit.api.state
    builds it forward-consistently); None keeps the continuous-yield carry.

    ``tau`` is the event-WEIGHTED variance years (volfit.calib.weighted_time);
    None means the calendar clock (tau = t). Total variance ``w`` is inverted
    from the price (clock-independent), so only the reported IV band uses tau:
    iv = sqrt(w / tau). Calendar ``t`` still drives de-Americanization and carry.
    """
    tv = t if tau is None or tau <= 0.0 else tau
    f, d = forward.forward, forward.discount
    scale = 1.0 / (d * f)
    # Tick-noise floor (module doc): only real-feed chains carry a tick size.
    price_floor = (
        TICK_FLOOR_TICKS * snapshot.tick_size if snapshot.tick_size else None
    )

    # Raw rows first: (k, strike, is_call, bid, mid, ask) in price space —
    # de-Americanization needs strikes and option types before normalization.
    # Every drop from here on is QUARANTINED with a reason (R1 item 6) — the
    # kept set is unchanged, the absences become auditable. The OTM-side skip
    # is structural (the ITM twin of every strike), not a quarantine.
    screened: list[ScreenedQuote] = []
    rows: list[tuple[float, float, bool, float, float, float]] = []
    for quote in snapshot.quotes_for(expiry):
        if quote.call_put != ("C" if quote.strike >= f else "P"):
            continue  # keep the OTM side only
        k = float(np.log(quote.strike / f))
        if quote.bid is None or quote.ask is None or quote.mid is None:
            screened.append(
                ScreenedQuote(quote.strike, quote.call_put, k, "missing_or_crossed")
            )
            continue
        if price_floor is not None and quote.bid <= price_floor:
            screened.append(ScreenedQuote(quote.strike, quote.call_put, k, "tick_floor"))
            continue  # tick-noise floor: the bid is at the quantum, not a market
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

    def _quarantine(mask: np.ndarray, reasons) -> None:
        """Record dropped rows; ``reasons`` is a string or per-row array."""
        for i in np.flatnonzero(mask):
            r = reasons if isinstance(reasons, str) else str(reasons[i])
            screened.append(
                ScreenedQuote(
                    float(strikes[i]), "C" if is_call[i] else "P", float(k_arr[i]), r
                )
            )

    # American chains: strip the early-exercise premium from bid/mid/ask.
    n_deam = 0
    n_deam_input = int(k_arr.size)
    eep_arr: np.ndarray | None = None
    if snapshot.exercise_style == "american" and t > 0.0:
        # Stage 3 pre-screen: drop rows the post-filters are guaranteed to drop
        # before the costly de-Am trees price them (byte-identical output).
        if prefilter and k_arr.size:
            pre, bid_ok = _pre_deam_screen(k_arr, bid, mid, is_call, scale)
            _quarantine(~pre & ~bid_ok, "nonpositive_bid")
            _quarantine(~pre & bid_ok, "wing")
            if pre.any() and not pre.all():
                k_arr, strikes, is_call = k_arr[pre], strikes[pre], is_call[pre]
                bid, mid, ask = bid[pre], mid[pre], ask[pre]
            n_deam_input = int(k_arr.size)
        eep_arr, n_deam = _early_exercise_premiums(
            snapshot.spot, is_call, strikes, k_arr, mid, f, d, t, cash_dividends
        )
        bid, mid, ask = bid - eep_arr, mid - eep_arr, ask - eep_arr

    # European pipeline: normalize, parity-shift puts -> normalized CALL prices c,
    # invert to total variance.
    shift = np.where(is_call, 0.0, 1.0 - np.exp(k_arr))
    c_bid = bid * scale + shift
    c_mid = mid * scale + shift
    c_ask = ask * scale + shift
    w_bid = implied_total_variance(k_arr, c_bid)
    w_mid = implied_total_variance(k_arr, c_mid)
    w_ask = implied_total_variance(k_arr, c_ask)

    keep = np.isfinite(w_bid) & np.isfinite(w_mid) & np.isfinite(w_ask)
    if not keep.any():
        raise ValueError(f"no quotes inside static bounds for {expiry.isoformat()}")
    # Name the static-bound drops (R1 item 6): a side at/below intrinsic (+ the
    # explicit INTRINSIC_TOL) means near-zero time value — no stable IV exists;
    # at/above the upper bound means a broken price; anything else failed the
    # inversion inside the bounds (w beyond W_MAX). Same drops, named.
    if not keep.all():
        intrinsic = np.maximum(1.0 - np.exp(k_arr), 0.0)
        lo = np.minimum(np.minimum(c_bid, c_mid), c_ask)
        hi = np.maximum(np.maximum(c_bid, c_mid), c_ask)
        reasons = np.where(
            lo <= intrinsic + INTRINSIC_TOL,
            "below_intrinsic",
            np.where(hi >= 1.0, "price_bound", "iv_unresolvable"),
        )
        _quarantine(~keep, reasons)
    # Wing filter: estimate ATM total variance from the surviving mids, then
    # drop strikes more than Z_MAX standard deviations from the forward.
    w_atm = float(np.interp(0.0, k_arr[keep], w_mid[keep]))
    wing_drop = keep & (np.abs(k_arr) > Z_MAX * np.sqrt(w_atm))
    _quarantine(wing_drop, "wing")
    keep &= ~wing_drop

    ks = k_arr[keep]
    w_bid_s, w_mid_s, w_ask_s = w_bid[keep], w_mid[keep], w_ask[keep]
    eep_s = eep_arr[keep] if eep_arr is not None else None
    strikes_s, is_call_s = strikes[keep], is_call[keep]
    # R3 (FINDINGS_calibration_arb): independent per-strike de-Am + max(EEP,0) can
    # leave the American call wings non-convex (butterfly-arbitrageable inputs).
    # Repair the WINGS only — the ATM core stays byte-identical — then re-invert the
    # (spread-preserving) repaired band. European / convex / disabled => no-op =>
    # byte-identical (the repair returns None and this whole block is skipped).
    if convex_deam and snapshot.exercise_style == "american" and t > 0.0:
        repaired = convex_wing_repair(ks, c_mid[keep], c_bid[keep], c_ask[keep], w_atm, f)
        if repaired is not None:
            delta = repaired - c_mid[keep]  # same per-strike shift on bid/ask => spread kept
            w_bid_r = implied_total_variance(ks, c_bid[keep] + delta)
            w_mid_r = implied_total_variance(ks, repaired)
            w_ask_r = implied_total_variance(ks, c_ask[keep] + delta)
            ok = np.isfinite(w_bid_r) & np.isfinite(w_mid_r) & np.isfinite(w_ask_r)
            if not ok.all():
                for i in np.flatnonzero(~ok):  # repaired band failed to re-invert
                    screened.append(
                        ScreenedQuote(
                            float(strikes_s[i]), "C" if is_call_s[i] else "P",
                            float(ks[i]), "iv_unresolvable",
                        )
                    )
            ks, w_bid_s, w_mid_s, w_ask_s = ks[ok], w_bid_r[ok], w_mid_r[ok], w_ask_r[ok]
            if eep_s is not None:
                eep_s = eep_s[ok]

    iv_mid_s = np.sqrt(w_mid_s / tv)
    return PreparedQuotes(
        t=t,
        forward=f,
        discount=d,
        k=ks,
        w_mid=w_mid_s,
        iv_bid=np.sqrt(w_bid_s / tv),
        iv_mid=iv_mid_s,
        iv_ask=np.sqrt(w_ask_s / tv),
        n_deamericanized=n_deam,
        n_deam_input=n_deam_input,
        tau=tv,
        screened=tuple(screened),
        eep=eep_s,
        vega_floored=int(
            np.count_nonzero(black_vega_sigma(ks, iv_mid_s, tv) < VEGA_FLOOR_DIAG)
        ),
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
            # The amended IV is in the displayed (weighted) clock, so the total
            # variance uses tau — consistent with w_mid = iv_mid^2 * tau.
            w[index] = edit.amended_iv**2 * prepared.tau
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
