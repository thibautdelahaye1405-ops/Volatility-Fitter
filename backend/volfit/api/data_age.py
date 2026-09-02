"""Data-age staleness of the loaded chains (the Massive-staleness slice).

Chain timestamps are honest about when the DATA is from (the WS-book fix
stamps provider tick times; REST/Yahoo/Bloomberg chains are stamped at fetch),
so age = wall clock − chain timestamp measures how old the quotes a view is
pricing really are. A premarket fetch off the delayed Massive book therefore
reads ~13 h, not "live".

Semantics — deliberately narrow so it never cries wolf:

- LIVE as-of only. Historical / prev-close / captured views are stale by
  CHOICE (the As-of selector already labels them); age is None there.
- Real-feed chains only. A snapshot alone qualifies via ``tick_size`` (set by
  every US real feed); chains from the non-US exchange adapters (Eurex / ASX /
  HKEX / SGX) legitimately carry ``tick_size=None`` (per-class ticks unknown)
  yet stamp a REAL market clock — e.g. a stale Eurex EOD settlement chain —
  so the state-level reads also admit any chain served by a real (non-
  synthetic) provider. Excluded either way: SyntheticProvider chains (their
  fixed-reference stamp would read years old) and zero-carry IV-synthesized
  chains (exact model prices, no market book).
- Levels: ``fresh`` under ``OptionsSettings.dataAgeAmberMin`` minutes,
  ``amber`` under ``dataAgeRedMin``, else ``red``. Red fails the quality
  report's publish-readiness; amber is advisory (shown, never gating).

Consumers: GET /datasources (the TopBar market pill + Calibrate hint),
GET /quality + the HTML export report (per-ticker age column, node issues).
"""

from __future__ import annotations

from datetime import datetime, timezone

from volfit.data.types import ChainSnapshot

#: Age levels in escalation order.
LEVELS = ("fresh", "amber", "red")


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_age(minutes: float) -> str:
    """Human age: '4m' / '25m' / '13.5h' / '3.2d'."""
    if minutes < 90.0:
        return f"{minutes:.0f}m"
    hours = minutes / 60.0
    if hours < 48.0:
        return f"{hours:.1f}h"
    return f"{hours / 24.0:.1f}d"


def chain_age_minutes(
    snapshot: ChainSnapshot | None,
    now: datetime | None = None,
    real_feed: bool = False,
) -> float | None:
    """Age of one chain in minutes, or None when age has no meaning: nothing
    loaded, an empty chain, or a chain with no market clock.

    ``tick_size`` set = a real feed (the snapshot-only discriminator; default
    behavior, unchanged). ``real_feed=True`` — asserted by the caller when the
    serving PROVIDER is a real feed (see ``ticker_ages``) — additionally
    admits tickless real chains (Eurex/ASX/HKEX/SGX set ``tick_size=None``:
    unknown per-class ticks, not exact prices), EXCEPT zero-carry chains: those
    are IV-synthesized exact model prices (Massive's gated-NBBO fallback) and
    deliberately stay out of the age signal."""
    if snapshot is None or not snapshot.quotes:
        return None
    if snapshot.tick_size is None and not (real_feed and not snapshot.zero_carry):
        return None
    age = ((now or _now_utc_naive()) - snapshot.timestamp).total_seconds() / 60.0
    return max(age, 0.0)


def age_level(age_min: float, amber_min: float, red_min: float) -> str:
    """'fresh' | 'amber' | 'red' for one age against the configured thresholds."""
    if age_min >= red_min:
        return "red"
    if age_min >= amber_min:
        return "amber"
    return "fresh"


def ticker_ages(state, now: datetime | None = None) -> dict[str, float]:
    """Per-ticker chain age (minutes) of the LOADED live chains.

    Empty when the as-of selection is not live (historical staleness is a
    choice, not a warning). Never fetches: only chains already in the state
    cache are aged, so this is as cheap as a status poll."""
    if state.as_of.mode != "live":
        return {}
    # A cached snapshot always comes from the TICKER's own provider (a pin, else
    # the default; a source change drops that ticker's chain caches), so the
    # provider kind is a sound per-ticker discriminator: any non-synthetic
    # provider is a real feed whose chains carry a market clock even without a
    # tick size (Eurex & co).
    from volfit.data.provider import SyntheticProvider

    now = now or _now_utc_naive()
    ages: dict[str, float] = {}
    for ticker in state.active_tickers():
        real_feed = not isinstance(state.provider_for(ticker), SyntheticProvider)
        age = chain_age_minutes(state.loaded_snapshot(ticker), now, real_feed=real_feed)
        if age is not None:
            ages[ticker] = age
    return ages


def universe_age(state, now: datetime | None = None) -> dict | None:
    """The TopBar / selector payload: worst loaded-chain age across the active
    universe, with its level and a human label. None when nothing applies
    (not live, nothing fetched, or only exact-price chains)."""
    ages = ticker_ages(state, now)
    if not ages:
        return None
    worst_ticker = max(ages, key=ages.get)
    worst = ages[worst_ticker]
    opts = state.options()
    return {
        "ageMin": round(worst, 1),
        "level": age_level(worst, opts.dataAgeAmberMin, opts.dataAgeRedMin),
        "label": format_age(worst),
        "worstTicker": worst_ticker,
    }
