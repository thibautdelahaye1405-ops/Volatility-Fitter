"""Six read-only Massive calls: SPX vs I:SPX spelling on the contracts reference and the
snapshot, and the ticker search under market=stocks vs market=indices. Never prints the key."""
import os, httpx
key = os.environ["VOLFIT_MASSIVE_KEY"].strip()
c = httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=20.0)
B = "https://api.massive.com"
def show(tag, r):
    try: b = r.json()
    except Exception: b = {"_text": r.text[:120]}
    res = b.get("results") or []
    print(f"[{tag}] HTTP {r.status_code} status={b.get('status')} n={len(res)} msg={b.get('message','') or b.get('error','')}")
    return res
for u in ("SPX", "I:SPX"):
    res = show(f"contracts underlying_ticker={u}", c.get(f"{B}/v3/reference/options/contracts",
        params={"underlying_ticker": u, "expired": "false", "order": "asc", "sort": "expiration_date", "limit": 3}))
    for x in res[:2]: print("     ", x.get("ticker"), x.get("underlying_ticker"), x.get("expiration_date"), x.get("exercise_style"))
for u in ("SPX", "I:SPX"):
    res = show(f"snapshot /v3/snapshot/options/{u}", c.get(f"{B}/v3/snapshot/options/{u}", params={"limit": 2}))
    for x in res[:1]:
        ua = x.get("underlying_asset") or {}; lq = x.get("last_quote") or {}
        print("     ", (x.get("details") or {}).get("ticker"), "underlying_asset=", {k: ua.get(k) for k in ("ticker","price","change_to_break_even")}, "last_quote=", {k: lq.get(k) for k in ("bid","ask","last_updated")})
for m in ("stocks", "indices"):
    res = show(f"tickers search=SPX market={m}", c.get(f"{B}/v3/reference/tickers", params={"search": "SPX", "market": m, "active": "true", "limit": 5}))
    print("     ", [(x.get("ticker"), x.get("name"), x.get("type")) for x in res[:5]])
