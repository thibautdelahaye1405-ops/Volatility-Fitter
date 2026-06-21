"""Bloomberg free-text symbol search via the //blp/instruments service.

Split out of bloomberg.py for the 400-line policy. One ``instrumentListRequest``
resolves a query ("Nvidia" / "NVDA") to Bloomberg securities ("NVDA US Equity").
The blpapi session is opened lazily and cached on the *provider* (so it is reused
across searches and torn down by the caller if a search fails); this function is
always invoked under the provider's search lock.

Both **equities/ETFs** and **indices** are searched (and merged), so non-US
stocks ("SAP GY Equity") and index underlyings ("SX5E Index", "UKX Index") are
both discoverable for the universe picker — the instrumentListRequest takes a
single ``yellowKeyFilter``, so one request is issued per yellow key and the hits
are **interleaved** (round-robin) so neither asset class crowds the other out of
the result limit.
"""

from __future__ import annotations

from itertools import zip_longest

from volfit.data.bloomberg_parse import normalize_security
from volfit.data.provider import SymbolMatch
from volfit.data.symbols import portable_ticker

#: Bloomberg security-search service (free-text symbol/name -> securities).
INSTRUMENTS_SERVICE = "//blp/instruments"

#: Yellow keys to search, each as ``(filter, type-label)``. Equities first — the
#: common ticker search ("AAPL") — then indices; results are INTERLEAVED in
#: ``_merge_matches`` so an index query still surfaces its index and an equity
#: query still surfaces equities (the previous concat-indices-first dropped every
#: equity off the end of the limit when the index filter returned loose matches).
_YK_FILTERS = (
    ("YK_FILTER_EQTY", "EQUITY"),
    ("YK_FILTER_INDX", "INDEX"),
)


def instrument_search(provider, blpapi, query: str, limit: int) -> list[SymbolMatch]:
    """Resolve a query to Bloomberg securities across equities + indices.

    Reuses ``provider._search_session`` if present, otherwise opens one. Raises
    on any session/service failure so the caller can drop the dead session and
    fall back to the base substring/echo search.
    """
    session = _ensure_session(provider, blpapi)
    service = session.getService(INSTRUMENTS_SERVICE)
    batches = [
        _run_filter(session, service, blpapi, query, limit, yk, label)
        for yk, label in _YK_FILTERS
    ]
    return _merge_matches(batches, limit)


def _ensure_session(provider, blpapi):
    """Lazily open (and cache on the provider) a blpapi instruments session."""
    if provider._search_session is None:
        options = blpapi.SessionOptions()
        options.setServerHost("localhost")
        options.setServerPort(8194)
        session = blpapi.Session(options)
        if not session.start() or not session.openService(INSTRUMENTS_SERVICE):
            raise RuntimeError("instrument search service unavailable")
        provider._search_session = session
    return provider._search_session


def _run_filter(
    session, service, blpapi, query: str, limit: int, yellow_key: str, label: str
) -> list[SymbolMatch]:
    """One instrumentListRequest for a single yellow key (equities or indices)."""
    request = service.createRequest("instrumentListRequest")
    request.set("query", query)
    request.set("maxResults", max(1, limit))
    try:
        request.set("yellowKeyFilter", yellow_key)
    except Exception:
        pass  # older API without the filter: take all yellow keys
    session.sendRequest(request)

    matches: list[SymbolMatch] = []
    while True:
        event = session.nextEvent(5000)
        for message in event:
            if not message.hasElement("results"):
                continue
            results = message.getElement("results")
            for i in range(results.numValues()):
                row = results.getValueAsElement(i)
                if not row.hasElement("security"):
                    continue
                security = portable_ticker(
                    normalize_security(row.getElementAsString("security"))
                )
                description = (
                    row.getElementAsString("description")
                    if row.hasElement("description")
                    else ""
                )
                matches.append(
                    SymbolMatch(symbol=security, name=description, type=label)
                )
        if event.eventType() == blpapi.Event.RESPONSE:
            break
    return matches


def _merge_matches(batches: list[list[SymbolMatch]], limit: int) -> list[SymbolMatch]:
    """Round-robin merge across the yellow-key batches, de-dup by symbol, trim.

    Interleaving (not concatenating one yellow key before the other) keeps BOTH
    asset classes in the top ``limit``: an equity query still surfaces equities
    even when the index filter also returns loose matches, and an index query
    still surfaces its index. ``zip_longest`` lets the richer batch fill the
    remaining slots, so a stock search with few index hits still returns mostly
    equities. Batches are consumed in the given order, so the first batch leads
    each round (equities, per ``_YK_FILTERS``).
    """
    out: list[SymbolMatch] = []
    seen: set[str] = set()
    for row in zip_longest(*batches):
        for match in row:
            if match is None or match.symbol in seen:
                continue
            seen.add(match.symbol)
            out.append(match)
    return out[:limit]
