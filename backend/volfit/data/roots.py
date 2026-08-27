"""Index option roots — the ONE parent ↔ sibling registry (workbench follow-on
"index-root discovery for snapshot files", 2026-08-27).

A cash index trades under several OCC roots: the AM-settled monthly root
(``SPX``) plus its PM-settled weekly / EOM siblings (``SPXW``; likewise
``NDX``/``NDXP``, ``RUT``/``RUTW``, ``XSP``/``XSPW``, ``VIX``/``VIXW``). A
snapshot file exported from a universe keyed ``SPXW`` must still be found when
the user types ``SPX`` — the app has no other alias mechanism. This module is
the shared table: ``volfit.data.cboe`` maps roots to CDN files with it,
``volfit.data.file.FileProvider`` resolves typed symbols through it, and the
snapshot export stamps each index ticker's parent ``root`` from it. Pure data
+ functions; the backtest layer keeps its own per-universe ``roots_for``.
"""

from __future__ import annotations

#: Every known cash-index root (parents AND their weekly / PM siblings).
#: Lifted from the Cboe adapter's table (``_ROOT`` files, European exercise).
INDEX_ROOTS: frozenset[str] = frozenset({
    "SPX", "SPXW", "XSP", "XSPW", "VIX", "VIXW", "RUT", "RUTW", "MRUT", "NDX", "NDXP",
    "DJX", "OEX", "XEO", "BXM", "BXD", "BXR", "PUT", "RXM", "VXX", "NANOS",
})

#: Weekly / PM sibling root → parent root; every other index root maps to
#: itself, so ``PARENT_OF.get(root, root)`` is the parent of ANY symbol.
PARENT_OF: dict[str, str] = {
    **{r: r for r in sorted(INDEX_ROOTS)},
    "SPXW": "SPX", "XSPW": "XSP", "VIXW": "VIX", "RUTW": "RUT", "NDXP": "NDX",
}


def normalize_root(symbol: str) -> str:
    """Bare upper-case root: strips a Bloomberg ``" Index"`` suffix and the
    ``^`` / ``_`` index prefixes (``"^SPX"``, ``"_SPX"``, ``"SPX Index"`` → ``SPX``)."""
    s = symbol.strip().upper()
    if s.endswith(" INDEX"):
        s = s[: -len(" INDEX")].strip()
    return s.lstrip("^").lstrip("_")


def is_index_root(symbol: str) -> bool:
    """Whether the symbol names a known cash-index root (parent or sibling)."""
    return normalize_root(symbol) in INDEX_ROOTS


def parent_root(root: str) -> str:
    """The parent index root of a symbol (``SPXW`` → ``SPX``; ``SPX`` → ``SPX``;
    a non-index symbol → itself, normalized)."""
    r = normalize_root(root)
    return PARENT_OF.get(r, r)


def roots_of(parent: str) -> tuple[str, ...]:
    """Every root of an index family, parent first then its siblings (sorted):
    ``roots_of("SPX")`` → ``("SPX", "SPXW")``; a non-index → ``(symbol,)``."""
    p = parent_root(parent)
    siblings = sorted(r for r, pr in PARENT_OF.items() if pr == p and r != p)
    return (p, *siblings)


def aliases(ticker: str) -> tuple[str, ...]:
    """The symbols that name the same index family as ``ticker``: itself
    first, then its parent (when different), then the other siblings. A
    non-index ticker aliases only itself."""
    t = normalize_root(ticker)
    if t not in INDEX_ROOTS:
        return (t,)
    return (t, *(r for r in roots_of(t) if r != t))
