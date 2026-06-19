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
are de-duplicated.
"""

from __future__ import annotations

from volfit.data.bloomberg_parse import normalize_security
from volfit.data.provider import SymbolMatch

#: Bloomberg security-search service (free-text symbol/name -> securities).
INSTRUMENTS_SERVICE = "//blp/instruments"

#: Yellow keys to search, each as ``(filter, type-label)``. Indices first so a
#: genuine index query ("DAX", "SX5E") is never crowded out of the result limit
#: by ETFs sharing the name; the index filter returns nothing for an equity
#: query, so plain stock searches are unaffected.
_YK_FILTERS = (
    ("YK_FILTER_INDX", "INDEX"),
    ("YK_FILTER_EQTY", "EQUITY"),
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
                security = normalize_security(row.getElementAsString("security"))
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
    """Flatten per-yellow-key result batches, de-duplicate by symbol, trim."""
    out: list[SymbolMatch] = []
    seen: set[str] = set()
    for batch in batches:
        for match in batch:
            if match.symbol in seen:
                continue
            seen.add(match.symbol)
            out.append(match)
    return out[:limit]
