"""Option-chain provider interface and an offline synthetic provider.

Design intent (ROADMAP Phase 3): all market-data sources (Yahoo scraper,
Bloomberg, Massive, ...) implement the small `OptionChainProvider` contract
so the rest of the stack — storage, forwards, calibration, API — is
provider-agnostic.  Real providers are added as optional plug-ins later.

`SyntheticProvider` exists for *offline development and tests*: it fabricates
a realistic, deterministic equity option chain from a built-in SVI-style
smile per expiry, priced through the normalized Black formula
(volfit.core.black, eq. (black) of Docs/lqd_model_note.tex).  Rates are zero
by construction (discount = 1, forward = spot), so put prices follow from
exact put-call parity and the implied-forward regression of
volfit.data.forwards must recover the spot — a useful self-test.
"""

from __future__ import annotations

import abc
import zlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np

from volfit.core.black import black_call
from volfit.data.types import ChainSnapshot, OptionQuote


@dataclass(frozen=True)
class SymbolMatch:
    """One symbol-search hit for the universe picker (symbol + display info)."""

    symbol: str
    name: str = ""
    type: str = ""  # EQUITY / ETF / INDEX, provider-defined
    exchange: str = ""


@dataclass(frozen=True)
class AsOf:
    """Which point in time a chain is requested as-of.

    - ``"live"``        the latest available chain (the default everywhere);
    - ``"prev_close"``  the prior session's closing chain (provider EOD settle);
    - ``"eod"``         the closing chain of the specific trading day ``on``.

    Captured-snapshot replay (loading a stored intraday chain from the VolStore)
    is handled by AppState, not the provider — providers only serve live + EOD.
    """

    mode: str = "live"  # "live" | "prev_close" | "eod"
    on: date | None = None  # required when mode == "eod"

# Synthetic expiry ladder: ~1M, 3M, 6M, 1Y from the reference date.
_EXPIRY_DAYS = (30, 91, 182, 365)

# Strike grid spans this moneyness range around spot.
_MONEYNESS_LO = 0.65
_MONEYNESS_HI = 1.40


class OptionChainProvider(abc.ABC):
    """Contract every market-data source must satisfy."""

    @abc.abstractmethod
    def list_tickers(self) -> list[str]:
        """Tickers this provider can serve option chains for."""

    @abc.abstractmethod
    def fetch_chain(
        self,
        ticker: str,
        expiries: list[date] | None = None,
        as_of: AsOf | None = None,
    ) -> ChainSnapshot:
        """Fetch the option chain for one underlying.

        ``expiries`` restricts the fetch to those expiry dates (the universe's
        per-ticker selection); ``None`` fetches the provider's natural ladder.
        ``as_of`` (None == live) selects a historical EOD chain — providers that
        only do live ignore non-live requests; check ``historical_modes`` first.
        """

    @abc.abstractmethod
    def available_expiries(self, ticker: str) -> list[date]:
        """All expiries the provider can serve for a ticker, cheaply (no chain
        fetch) — the full list the universe picker chooses from."""

    def spot(self, ticker: str, expiries: list[date] | None = None) -> float:
        """Current spot of the underlying, for real-time spot polling.

        The default re-reads ``fetch_chain``'s spot (correct for every provider,
        though not the cheapest); live providers with a lightweight quote feed
        override this. Synthetic chains are static, so polling reports no move.
        """
        return float(self.fetch_chain(ticker, expiries).spot)

    def historical_modes(self) -> set[str]:
        """As-of modes this provider supports (default: live only)."""
        return {"live"}

    def available_history(self, ticker: str) -> list[date]:
        """Past trading days this provider can serve an EOD chain for (default:
        none). Newest last; the as-of picker offers these as 'day (close)'."""
        return []

    def feed_status(self) -> tuple[str, str]:
        """Liveness of this source as ``(level, detail)`` for the Data Source
        selector. ``level`` is "green" (real-time), "amber" (delayed) or "red"
        (unavailable). The default reports an always-available offline source;
        live providers override with a cheap probe.
        """
        return ("green", "available")

    def search_symbols(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        """Resolve a free-text query (symbol or name) to candidate symbols.

        Default: a substring match over ``list_tickers`` plus the raw query as
        a candidate (providers that can quote any symbol, e.g. the synthetic
        and Yahoo, can then add it directly). Live providers override this with
        a real catalog search (see YahooProvider). Returns at most ``limit``.
        """
        q = query.strip().upper()
        if not q:
            return []
        out = [SymbolMatch(symbol=t) for t in self.list_tickers() if q in t.upper()]
        bare = q.lstrip("^").replace(".", "").replace("-", "")
        if q not in {m.symbol for m in out} and bare.isalnum() and len(q) <= 6:
            out.append(SymbolMatch(symbol=q))  # let any plausible symbol be added
        return out[:limit]


def _svi_total_variance(k: np.ndarray, t: float) -> np.ndarray:
    """Built-in SVI smile in total variance, w(k) = a + b(rho(k-m) + sqrt((k-m)^2 + s^2)).

    Parameters are chosen per expiry so that the ATM vol decays gently with
    maturity, the skew is negative (equity-like) and w(k) > 0 everywhere
    (a > 0, b > 0, |rho| < 1 guarantee positivity).
    """
    atm_vol = 0.20 + 0.03 * np.exp(-2.0 * t)
    w_atm = atm_vol * atm_vol * t
    b = 0.8 * w_atm
    rho, m, s = -0.4, 0.0, 0.15
    # a is set so that w(m=0) equals the targeted ATM total variance.
    a = w_atm - b * s
    km = k - m
    return a + b * (rho * km + np.sqrt(km * km + s * s))


def _nice_step(raw: float) -> float:
    """Round a raw strike step onto the usual 1-2-5 exchange ladder."""
    magnitude = 10.0 ** np.floor(np.log10(raw))
    for mult in (1.0, 2.0, 5.0, 10.0):
        if raw <= mult * magnitude:
            return float(mult * magnitude)
    return float(10.0 * magnitude)


class SyntheticProvider(OptionChainProvider):
    """Deterministic synthetic chains for offline development and tests.

    Every chain is fully reproducible: the per-ticker spot is a CRC32 hash of
    the ticker (stable across processes, unlike built-in `hash`), and the
    activity fields (volume, open interest) come from a
    `numpy.random.RandomState` seeded with `seed ^ crc32(ticker)`.

    Bid/ask are placed *symmetrically* around the exact Black model price so
    that mids reproduce the model to machine precision (parity tests rely on
    this); the half-spread widens quadratically in log-moneyness to mimic
    real wing illiquidity, and is capped so bids stay strictly positive.
    """

    def __init__(
        self,
        reference_date: date,
        tickers: tuple[str, ...] = ("ALPHA", "BETA", "GAMMA"),
        seed: int = 0,
    ) -> None:
        self.reference_date = reference_date
        self._tickers = list(tickers)
        self._seed = seed

    def list_tickers(self) -> list[str]:
        return list(self._tickers)

    def feed_status(self) -> tuple[str, str]:
        """Always available — deterministic offline chains, no network."""
        return ("green", "synthetic (offline)")

    def available_expiries(self, ticker: str) -> list[date]:
        """The synthetic ladder: ~1M, 3M, 6M, 1Y from the reference date."""
        return [self.reference_date + timedelta(days=d) for d in _EXPIRY_DAYS]

    def fetch_chain(
        self,
        ticker: str,
        expiries: list[date] | None = None,
        as_of: AsOf | None = None,
    ) -> ChainSnapshot:
        """Build the synthetic chain: calls and puts on a strike grid per expiry
        (the natural 4-expiry ladder, or just ``expiries`` when given). The
        synthetic source is live-only, so ``as_of`` is ignored."""
        tick_hash = zlib.crc32(ticker.encode("utf-8"))
        spot = 50.0 + (tick_hash % 4000) / 10.0  # deterministic spot in [50, 449.9]
        rng = np.random.RandomState((self._seed ^ tick_hash) & 0x7FFFFFFF)
        timestamp = datetime.combine(self.reference_date, time(16, 0))

        step = _nice_step(spot / 25.0)
        strikes = np.arange(
            np.ceil(_MONEYNESS_LO * spot / step) * step,
            _MONEYNESS_HI * spot + 0.5 * step,
            step,
        )

        chosen = self.available_expiries(ticker) if expiries is None else list(expiries)
        quotes: list[OptionQuote] = []
        for expiry in chosen:
            t = max((expiry - self.reference_date).days, 0) / 365.0
            if t <= 0.0:
                continue
            k = np.log(strikes / spot)
            w = _svi_total_variance(k, t)

            # Zero rates: discount = 1, F = spot, so price = spot * B(k, w)
            # and the put follows from parity P = C - (F - K).
            call_mid = spot * black_call(k, w)
            put_mid = call_mid - (spot - strikes)

            # Half-spread: vol-proportional base, widening in the wings,
            # capped below the mid so the bid stays strictly positive.
            half = 0.0025 * spot * np.sqrt(w) * (1.0 + 4.0 * k * k)
            half_call = np.minimum(half, 0.95 * call_mid)
            half_put = np.minimum(half, 0.95 * put_mid)

            # Synthetic activity: concentrated near the money.
            lam = 500.0 * np.exp(-8.0 * np.abs(k)) + 1.0
            volume = rng.poisson(lam)
            open_interest = rng.poisson(10.0 * lam)

            for i, strike in enumerate(strikes):
                for cp, mid, h in (
                    ("C", float(call_mid[i]), float(half_call[i])),
                    ("P", float(put_mid[i]), float(half_put[i])),
                ):
                    quotes.append(
                        OptionQuote(
                            ticker=ticker,
                            expiry=expiry,
                            strike=float(strike),
                            call_put=cp,
                            bid=mid - h,
                            ask=mid + h,
                            last=mid,
                            volume=int(volume[i]),
                            open_interest=int(open_interest[i]),
                            timestamp=timestamp,
                        )
                    )

        return ChainSnapshot(ticker=ticker, spot=spot, timestamp=timestamp, quotes=quotes)
