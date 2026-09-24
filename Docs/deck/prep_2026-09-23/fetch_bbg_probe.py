"""Bloomberg live probe: status call, SPY chain listing (3 bds), SPY 2-expiry
and monthly-ladder quotes (bdp), SPX listing + 2 expiries. Every bds/bdp is
timed and its security count recorded through a proxy over xbbg.blp.
Run from backend\ with the venv python (Terminal must be up)."""
import os, sys, time
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from volfit.data.bloomberg import BloombergProvider, _default_blp

log = []
class TimedBlp:
    def __init__(self, blp): self._b = blp
    def __getattr__(self, name): return getattr(self._b, name)
    def bdp(self, securities, fields, **kw):
        secs = [securities] if isinstance(securities, str) else list(securities)
        t = time.perf_counter()
        try:
            out = self._b.bdp(secs, fields, **kw); ok = "ok"
        except Exception as exc:
            ok = f"FAIL {str(exc).strip().splitlines()[-1][:160]}"; out = None
        log.append(("bdp", len(secs), fields if isinstance(fields, str) else ",".join(fields), round(time.perf_counter()-t, 2), ok))
        if out is None: raise RuntimeError(ok)
        return out
    def bds(self, security, field, **kw):
        t = time.perf_counter()
        try:
            out = self._b.bds(security, field, **kw); ok = "ok"
        except Exception as exc:
            ok = f"FAIL {str(exc).strip().splitlines()[-1][:160]}"; out = None
        log.append(("bds", security, field + (f" {kw.get('overrides')}" if kw.get('overrides') else ""), round(time.perf_counter()-t, 2), ok))
        if out is None: raise RuntimeError(ok)
        return out

def dump(tag):
    print(f"--- {tag}")
    for row in log: print("   ", row)
    log.clear()

p = BloombergProvider(["SPY", "SPX"], blp_module=TimedBlp(_default_blp()))
t = time.perf_counter(); print("feed_status", p.feed_status(), f"{time.perf_counter()-t:.2f}s"); dump("status")

t = time.perf_counter(); exps = p.available_expiries("SPY"); dt = time.perf_counter()-t
chain = p._chain("SPY")
print(f"SPY listing: {len(exps)} expiries, {len(chain)} contracts, {dt:.2f}s"); dump("SPY listing")

def two_sided(s): return sum(1 for q in s.quotes if q.bid is not None and q.ask is not None)
t = time.perf_counter(); s = p.fetch_chain("SPY", exps[:2]); dt = time.perf_counter()-t
print(f"SPY 2 expiries {exps[:2]}: {len(s.quotes)} quotes ({two_sided(s)} two-sided), spot {s.spot}, {dt:.2f}s"); dump("SPY 2 exp")

monthlies = [e for e in exps if e.weekday() == 4 and 15 <= e.day <= 21]
t = time.perf_counter(); s = p.fetch_chain("SPY", monthlies); dt = time.perf_counter()-t
print(f"SPY monthly ladder {len(monthlies)} rungs: {len(s.quotes)} quotes ({two_sided(s)} two-sided), {dt:.2f}s"); dump("SPY monthlies")

t = time.perf_counter(); xe = p.available_expiries("SPX"); dt = time.perf_counter()-t
xc = p._chain("SPX"); roots = p._roots_cache.get("SPX", {})
from collections import Counter
print(f"SPX listing: {len(xe)} expiries, {len(xc)} contracts, roots {Counter(roots.values())}, {dt:.2f}s"); dump("SPX listing")
t = time.perf_counter(); s = p.fetch_chain("SPX", xe[:2]); dt = time.perf_counter()-t
print(f"SPX 2 expiries {xe[:2]}: {len(s.quotes)} quotes ({two_sided(s)} two-sided), spot {s.spot}, {dt:.2f}s"); dump("SPX 2 exp")
xm = [e for e in xe if e.weekday() == 4 and 15 <= e.day <= 21]
n_full = sum(1 for c in xc if c.expiry in set(xm))
print(f"SPX monthly ladder would be {len(xm)} rungs / {n_full} contracts before the strike window (NOT quoted: quota)")
print("feed_status after:", p.feed_status())
