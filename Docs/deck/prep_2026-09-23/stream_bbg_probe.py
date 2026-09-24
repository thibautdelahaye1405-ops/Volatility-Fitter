"""Short Bloomberg //blp/mktdata probe (8 s, 4 securities, interval=1) through the
app's own BloombergSubscription + a //blp/mktlist openService check. Read-only,
closes the session at the end."""
import time
from volfit.data.bloomberg_stream import BbgBook, BloombergSubscription

secs = ["SPY US Equity", "SPX Index", "SPY US 10/16/26 C660 Equity", "SPY US 10/16/26 P660 Equity"]
book = BbgBook()
sub = BloombergSubscription(secs, book, interval=1.0)
t0 = time.time(); sub.start(); time.sleep(8.0)
print(f"after {time.time()-t0:.1f}s: running={sub.is_running()} last_error={sub.last_error!r} started={book.started()} "
      f"failures={book.failures()} size={book.size()} newest_ts={book.newest_ts()} delayed={book.delayed()}")
for s in secs:
    print(" ", s, "->", book.quote(s))
sub.stop(); time.sleep(0.5)
try:
    import blpapi
    opts = blpapi.SessionOptions(); opts.setServerHost("localhost"); opts.setServerPort(8194)
    s = blpapi.Session(opts); print("blpapi session start:", s.start())
    for svc in ("//blp/mktdata", "//blp/mktlist", "//blp/refdata"):
        print(f"  openService({svc}):", s.openService(svc))
    # a chain subscription on the market-list service (format per the Enterprise guide)
    subs = blpapi.SubscriptionList()
    subs.add("//blp/mktlist/chain/bsym/US/SPY", "", "", blpapi.CorrelationId("chain"))
    s.subscribe(subs); t1 = time.time(); seen = []
    while time.time() - t1 < 4.0:
        ev = s.nextEvent(500)
        for msg in ev:
            seen.append((ev.eventType(), str(msg.messageType())))
            if len(seen) <= 3: print("   mktlist msg:", str(msg)[:400].replace("\n", " | "))
    print("  mktlist events:", seen[:8], "total", len(seen))
    s.stop()
except Exception as exc:
    print("blpapi direct probe error:", repr(exc)[:200])
