"""Read-only probes of the free sources for SPX: Cboe _SPX, Nasdaq SPX, Yahoo ^SPX."""
import json, time, collections
import httpx
from volfit.data.occ import parse_option_symbol

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) volfit/1.0", "Accept": "application/json, text/plain, */*"}
c = httpx.Client(timeout=40.0, headers=H, follow_redirects=True)

# 1. Cboe _SPX
t0 = time.time()
r = c.get("https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json")
dt = time.time() - t0
print(f"[cboe _SPX] HTTP {r.status_code} bytes={len(r.content)} {dt:.1f}s")
if r.status_code == 200:
    p = r.json(); d = p["data"]; opts = d["options"]
    roots = collections.Counter(); exps = set(); two = 0
    for o in opts:
        try:
            occ = parse_option_symbol("O:" + o["option"])
        except ValueError:
            continue
        roots[occ.underlying] += 1; exps.add(occ.expiry)
        if (o.get("bid") or 0) > 0 and (o.get("ask") or 0) > 0: two += 1
    print(f"   timestamp={p.get('timestamp')} security_type={d.get('security_type')} spot={d.get('current_price')} contracts={len(opts)} two_sided={two} expiries={len(exps)} roots={dict(roots)}")
for sym in ("_VIX", "_NDX", "_RUT", "_XSP"):
    r = c.get(f"https://cdn.cboe.com/api/global/delayed_quotes/quotes/{sym}.json")
    print(f"[cboe {sym} quote] HTTP {r.status_code} price={(r.json().get('data') or {}).get('current_price') if r.status_code==200 else None}")

# 2. Nasdaq SPX / NDX
for sym, ac in (("SPX", "index"), ("NDX", "index"), ("SPY", "etf")):
    url = f"https://api.nasdaq.com/api/quote/{sym}/option-chain?assetclass={ac}&limit=0&fromdate=all&todate=undefined&excode=oprac&callput=callput&money=all&type=all"
    try:
        r = c.get(url, headers={**H, "Accept-Language": "en-US,en;q=0.9"})
        body = r.json() if r.status_code == 200 else {}
        rows = ((body.get("data") or {}).get("table") or {}).get("rows") or []
        print(f"[nasdaq {sym}/{ac}] HTTP {r.status_code} rCode={(body.get('status') or {}).get('rCode')} rows={len(rows)} msg={(body.get('status') or {}).get('bCodeMessage')}")
    except Exception as e:
        print(f"[nasdaq {sym}/{ac}] FAILED {type(e).__name__}: {e}")

# 3. Yahoo ^SPX via yfinance (what YahooProvider uses)
try:
    import yfinance as yf
    for sym in ("^SPX", "^GSPC"):
        t = yf.Ticker(sym)
        try:
            ex = t.options
            print(f"[yahoo {sym}] expiries={len(ex)} first={ex[:3]}")
            if ex:
                ch = t.option_chain(ex[1] if len(ex) > 1 else ex[0])
                calls = ch.calls
                nb = int(((calls['bid']>0)&(calls['ask']>0)).sum())
                print(f"   {ex[1] if len(ex)>1 else ex[0]}: calls={len(calls)} two_sided_calls={nb} sample_syms={list(calls['contractSymbol'][:2])}")
        except Exception as e:
            print(f"[yahoo {sym}] FAILED {type(e).__name__}: {e}")
except ImportError as e:
    print("yfinance missing", e)
