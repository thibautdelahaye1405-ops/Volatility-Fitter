"""Per-expiry strike windows for chain requests — one rule for every provider.

Why a window at all: a liquid underlying lists hundreds of strikes per expiry,
most of them far outside anything the fitter keeps. The quote prep
(volfit.api.quotes) drops every quote beyond ``Z_MAX`` = 4 ATM standard
deviations, |ln(K/F)| > 4·sqrt(w_atm), so strikes past that band cost a
request (a Massive snapshot page, a METERED Bloomberg security, a websocket
subscription slot) and never reach a fit. A request window that CONTAINS the
prep's band leaves every fit byte-identical while cutting the pages, hits and
subscriptions by a large factor on the short rungs, where the fittable band is
a few percent wide.

The rule (``strike_bounds``): keep strikes with
    |ln(K / S)| <= half_width(T),
    half_width(T) = clip(z · sigma_ref · sqrt(max(T, 1 day)), floor, cap),
with ``sigma_ref`` = 1.0 (a 100 % reference vol), ``z`` = ``Z_MAX``, a 5 %
floor (a 0DTE still gets a usable belly) and a cap of 3.0 in log-moneyness
(strikes from S/20 to 20·S — a sanity bound no listed ladder reaches: SPY's
one-year ladder stops near S/7.7, and a 2.0 cap measured on 2026-09-24
dropped 11 of those deep strikes and moved the rung's parity forward by
1.4 bp, because the forward regression weighs every paired strike). Containment,
exactly: the prep keeps |ln(K/F)| <= 4·sigma_atm·sqrt(T), i.e. |ln(K/S)| <=
4·sigma_atm·sqrt(T) + |ln(F/S)|, so the window contains every kept quote
whenever
    4·sigma_atm·sqrt(T) + |ln(F/S)| <= half_width(T).
Below the cap that is every name whose ATM vol sits under sigma_ref by the
carry margin (a 90 % name with 2 % of carry, say); the cap binds only past
0.56 years at sigma_ref = 1 and there admits ATM vols up to ~75 % at one
year. ``sigma_ref=None`` disables the window (the whole listed ladder). Note
that at sigma_ref = 1 the window is nearly inert on an index ETF's listed
ladder (its strikes already sit inside a 100 %-vol band): the saving is on
short rungs and on metered / subscription-capped sources; a per-name
sigma_ref from the last fit's ATM vol is the lever for more (a rider).

Providers pass the spot they have (the last fetch, the book, one cheap probe)
and the expiry; the window is deliberately spot-centred, not forward-centred:
the forward drift over any listed horizon is far inside the margin the 100 %
reference vol leaves.
"""

from __future__ import annotations

import math
from datetime import date

#: The prep's wing cut in ATM standard deviations (volfit.api.quotes.Z_MAX).
Z_MAX = 4.0
#: Reference ATM vol the window is sized for (contains the prep's band for any
#: name whose ATM vol is at most this).
DEFAULT_SIGMA_REF = 1.0
#: Half-width floor / cap in log-moneyness units.
HALF_WIDTH_FLOOR = 0.05
HALF_WIDTH_CAP = 3.0


def half_width(
    expiry: date,
    today: date,
    sigma_ref: float | None = DEFAULT_SIGMA_REF,
    z: float = Z_MAX,
    floor: float = HALF_WIDTH_FLOOR,
    cap: float = HALF_WIDTH_CAP,
) -> float | None:
    """The window's half-width in log-moneyness for ``expiry`` seen from
    ``today`` (None = no window). Time is calendar days / 365 floored at one
    day, so a same-day expiry still gets the floor-or-better belly."""
    if sigma_ref is None or sigma_ref <= 0.0:
        return None
    days = max((expiry - today).days, 1)
    raw = z * sigma_ref * math.sqrt(days / 365.0)
    return min(max(raw, floor), cap)


def strike_bounds(
    spot: float,
    expiry: date,
    today: date,
    sigma_ref: float | None = DEFAULT_SIGMA_REF,
    **kwargs,
) -> tuple[float, float] | None:
    """``(lo, hi)`` strike bounds for ``expiry`` around ``spot`` — inclusive
    bounds a provider passes as ``strike >= lo and strike <= hi`` (Massive's
    ``strike_price.gte/lte`` filters, a Bloomberg security filter, a
    subscription plan). None when the window is off or the spot is unusable
    (the caller requests the whole ladder)."""
    if spot is None or not (spot > 0.0) or not math.isfinite(spot):
        return None
    hw = half_width(expiry, today, sigma_ref, **kwargs)
    if hw is None:
        return None
    return (spot * math.exp(-hw), spot * math.exp(hw))


def inside(strike: float, bounds: tuple[float, float] | None) -> bool:
    """Whether ``strike`` lies inside ``bounds`` (everything is inside None)."""
    if bounds is None:
        return True
    lo, hi = bounds
    return lo <= strike <= hi
