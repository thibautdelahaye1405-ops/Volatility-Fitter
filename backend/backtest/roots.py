"""OCC option-root resolution for the intraday capture twins (V3.8 rider
"SPX/SPXW multi-root intraday discovery").

An index trades under several OCC roots — SPX as the AM-settled ``SPX``
monthlies plus the PM-settled ``SPXW`` weeklies/EOM (likewise NDX/NDXP,
RUT/RUTW) — while an ETF / single name is one root equal to its ticker. The
daily capture reads that split from ``backtest.universe``; this module gives
both intraday twins (``capture_intraday`` flat files, ``capture_intraday_rest``)
the same answer plus a CLI override.

Resolution order: explicit override -> the PILOT/FULL registry -> ``(ticker,)``.
Every ticker outside the registry (SPY/QQQ/IWM, the 0DTE pilot) resolves
exactly as before, so the default capture path stays byte-identical.

Same-date collision policy (v1): when two roots list the SAME expiry date, the
root listed FIRST in the roots tuple wins that date and the other roots'
contracts are dropped (``SPX`` before ``SPXW`` keeps the standard AM monthly on
a third Friday). The drop is recorded in the fixture (``meta.rootCollisions``).
The AM/PM same-date expiry-key redesign is a separate recorded rider.
"""

from __future__ import annotations

from datetime import date

from backtest.universe import FULL, PILOT, AssetSpec

#: ticker -> AssetSpec over both universes (identical specs where they overlap).
_REGISTRY: dict[str, AssetSpec] = {a.ticker: a for a in (*PILOT, *FULL)}


def roots_for(ticker: str, override: dict[str, tuple[str, ...]] | None = None) -> tuple[str, ...]:
    """The OCC roots to discover for ``ticker``: override, registry, or itself."""
    key = ticker.upper()
    if override and key in override:
        return tuple(r.upper() for r in override[key])
    spec = _REGISTRY.get(key)
    return tuple(spec.option_roots) if spec is not None else (ticker,)


def exercise_style_for(ticker: str, override: dict[str, tuple[str, ...]] | None = None) -> str:
    """``"european"`` for registry index specs, else ``"american"``. A roots
    override re-routes discovery only — it never changes the style (add a new
    European name to the universe registry instead)."""
    del override  # accepted for call symmetry with roots_for
    spec = _REGISTRY.get(ticker.upper())
    return spec.exercise_style if spec is not None else "american"


#: ``--roots`` grammar: ``TICKER=ROOT,ROOT;TICKER=ROOT`` — ``;`` between
#: tickers, ``,`` between roots. Both are shell-active in PowerShell (``;`` ends
#: a statement, a bare ``,`` builds an array), so SINGLE-QUOTE the value there:
#: ``--roots 'SPX=SPX,SPXW;NDX=NDX,NDXP'``. Single quotes are literal in
#: PowerShell and bash alike, which is why this pair beats whitespace. The
#: flag may also be repeated (one ticker per flag); callers join with ``;``.
def parse_roots_arg(text: str | None) -> dict[str, tuple[str, ...]]:
    """Parse the ``--roots`` override; ``None``/blank -> ``{}`` (no override)."""
    out: dict[str, tuple[str, ...]] = {}
    for group in (text or "").split(";"):
        group = group.strip()
        if not group:
            continue
        ticker, sep, roots = group.partition("=")
        names = tuple(r.strip().upper() for r in roots.split(",") if r.strip())
        if not sep or not ticker.strip() or not names:
            raise ValueError(f"bad --roots group {group!r}: expected TICKER=ROOT[,ROOT]")
        out[ticker.strip().upper()] = names
    return out


def resolve_expiry_roots(
    boards: dict[str, set[date]], roots: tuple[str, ...]
) -> tuple[dict[date, str], list[dict]]:
    """Apply the same-date collision policy to per-root expiry boards.

    Returns ``(expiry -> winning root, collisions)`` where each collision is
    ``{"expiry": iso, "kept": root, "dropped": [roots]}`` in expiry order."""
    expiry_root: dict[date, str] = {}
    collisions: list[dict] = []
    for e in sorted({e for b in boards.values() for e in b}):
        holders = [r for r in roots if e in boards.get(r, ())]
        expiry_root[e] = holders[0]
        if len(holders) > 1:
            collisions.append({"expiry": e.isoformat(), "kept": holders[0],
                               "dropped": holders[1:]})
    return expiry_root, collisions


def root_meta(ticker: str, roots: tuple[str, ...], expiry_root: dict[date, str],
              collisions: list[dict]) -> dict:
    """The fixture's ``meta`` block — EMPTY (no key written) for the plain
    single-root capture, so single-root fixtures keep their exact key set."""
    if tuple(roots) == (ticker,):
        return {}
    meta = {"roots": list(roots),
            "expiryRoots": {e.isoformat(): r for e, r in sorted(expiry_root.items())}}
    if collisions:
        meta["rootCollisions"] = collisions
    return meta
