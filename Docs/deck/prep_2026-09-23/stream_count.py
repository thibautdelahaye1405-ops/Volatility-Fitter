"""Contract counts + book-merge cost for the streaming universe (READ-ONLY).

Reads the Massive key from restart.local.ps1 in-process (never printed), lists
the contracts the app would subscribe (REST /v3/reference/options/contracts,
the same call MassiveProvider.option_tickers makes), for the running app's
selected expiries (GET /universe on :8000) and for the FULL ladder, then times
MassiveProvider._chain_from_book over a synthetic-filled LiveBook. No websocket
is opened (one connection per cluster per account: it would drop the app's).
"""
import json, re, time, tracemalloc, urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

from volfit.data.massive import MassiveProvider
from volfit.data.massive_ws import LiveBook, QuoteTick

src = Path(r"C:\Users\thiba\vol-fitter\restart.local.ps1").read_text(encoding="utf-8", errors="ignore")
def envval(name):
    m = re.search(r"\$env:%s\s*=\s*['\"]([^'\"]+)['\"]" % name, src)
    return m.group(1).strip() if m else ""
key, ws = envval("VOLFIT_MASSIVE_KEY"), envval("VOLFIT_MASSIVE_WS_URL")
print("key present:", bool(key), "| ws override host:", ws.split("://")[-1].split("/")[0] if ws else None)

prov = MassiveProvider(["SPY", "NVDA", "SPX"], api_key=key, ws_url=ws or None)
print("ws candidate clusters:", prov._ws_urls())

uni = json.load(urllib.request.urlopen("http://127.0.0.1:8000/universe", timeout=10))
sel = {t: [date.fromisoformat(e["expiry"]) for e in uni["expiries"][t]] for t in uni["tickers"]}

for t in ["SPY", "NVDA", "SPX"]:
    t0 = time.perf_counter()
    allc = prov._intraday_contracts(t, None)
    dt = time.perf_counter() - t0
    by_exp = Counter(c["expiry"] for c in allc)
    cp = Counter(c["call_put"] for c in allc)
    print(f"\n{t}: FULL ladder {len(allc):,} contracts over {len(by_exp)} expiries (C {cp['C']:,} / P {cp['P']:,}); REST listing {dt:.1f} s")
    near = sorted(by_exp)[:6]
    print("  nearest 6 expiries:", ", ".join(f"{e.isoformat()}={by_exp[e]}" for e in near))
    if t in sel:
        t0 = time.perf_counter()
        subset = prov._intraday_contracts(t, sel[t])
        dt = time.perf_counter() - t0
        per = Counter(c["expiry"] for c in subset)
        print(f"  APP SELECTION {len(sel[t])} expiries -> {len(subset):,} contracts to subscribe (cached listing read {dt*1e3:.1f} ms)")
        print("  per selected expiry:", ", ".join(f"{e.isoformat()}={per[e]}" for e in sorted(per)))
        print(f"  subscribe frame size: {len(json.dumps({'action':'subscribe','params':','.join('Q.'+c['ticker'] for c in subset)}))/1024:.0f} KB")

# --- book merge cost: SPY full ladder + app selection on a synthetic book
S = 660.0
def fill(book, contracts):
    ts = 1758600000000000000
    with book._lock:
        for c in contracts:
            K = c["strike"]
            intrinsic = max(S - K, 0.0) if c["call_put"] == "C" else max(K - S, 0.0)
            mid = intrinsic + 1.0
            book._quotes[c["ticker"]] = QuoteTick(bid=round(mid - 0.05, 2), ask=round(mid + 0.05, 2), ts=ts)
for label, exps in (("SPY app selection", sel.get("SPY")), ("SPY full ladder", None)):
    contracts = prov._intraday_contracts("SPY", exps)
    tracemalloc.start()
    book = LiveBook(); fill(book, contracts)
    cur, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    prov._live_book = book
    prov._chain_from_book("SPY", exps)  # warm
    t0 = time.perf_counter(); n = 5
    for _ in range(n):
        chain = prov._chain_from_book("SPY", exps)
    dt = (time.perf_counter() - t0) / n
    nearest = sorted({c["expiry"] for c in contracts})[:1]
    t0 = time.perf_counter(); ch1 = prov._chain_from_book("SPY", nearest); dt1 = time.perf_counter() - t0
    print(f"\n{label}: {len(contracts):,} contracts -> book {cur/1e6:.1f} MB; _chain_from_book {dt*1e3:.0f} ms per read "
          f"({len(chain.quotes):,} quotes, spot {chain.spot:.2f}); one-expiry read (SSE 1 Hz path) {dt1*1e3:.1f} ms ({len(ch1.quotes)} quotes)")
