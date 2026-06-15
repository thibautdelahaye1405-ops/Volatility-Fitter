"""Bloomberg free-text symbol search via the //blp/instruments service.

Split out of bloomberg.py for the 400-line policy. One ``instrumentListRequest``
resolves a query ("Nvidia" / "NVDA") to Bloomberg securities ("NVDA US Equity").
The blpapi session is opened lazily and cached on the *provider* (so it is reused
across searches and torn down by the caller if a search fails); this function is
always invoked under the provider's search lock.
"""

from __future__ import annotations

from volfit.data.bloomberg_parse import normalize_security
from volfit.data.provider import SymbolMatch

#: Bloomberg security-search service (free-text symbol/name -> securities).
INSTRUMENTS_SERVICE = "//blp/instruments"


def instrument_search(provider, blpapi, query: str, limit: int) -> list[SymbolMatch]:
    """One instrumentListRequest against //blp/instruments (call under lock).

    Reuses ``provider._search_session`` if present, otherwise opens one. Raises
    on any session/service failure so the caller can drop the dead session and
    fall back to the base substring/echo search.
    """
    if provider._search_session is None:
        options = blpapi.SessionOptions()
        options.setServerHost("localhost")
        options.setServerPort(8194)
        session = blpapi.Session(options)
        if not session.start() or not session.openService(INSTRUMENTS_SERVICE):
            raise RuntimeError("instrument search service unavailable")
        provider._search_session = session
    service = provider._search_session.getService(INSTRUMENTS_SERVICE)
    request = service.createRequest("instrumentListRequest")
    request.set("query", query)
    request.set("maxResults", max(1, limit))
    try:
        request.set("yellowKeyFilter", "YK_FILTER_EQTY")  # equities/ETFs
    except Exception:
        pass  # older API without the filter: take all yellow keys
    provider._search_session.sendRequest(request)

    matches: list[SymbolMatch] = []
    while True:
        event = provider._search_session.nextEvent(5000)
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
                    SymbolMatch(symbol=security, name=description, type="EQUITY")
                )
        if event.eventType() == blpapi.Event.RESPONSE:
            break
    return matches[:limit]
