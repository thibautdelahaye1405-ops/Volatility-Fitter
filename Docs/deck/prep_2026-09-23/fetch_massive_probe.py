"""Massive REST probe (read-only, ~8 calls): status-probe cost, listing page
count, snapshot page-size clamp, per-page latency, rate-limit headers.
Run from backend\ with the venv python after dot-sourcing restart.local.ps1.
Never prints the key."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from volfit.data.massive import MassiveProvider, _SNAPSHOT_LIMIT

key = os.environ.get("VOLFIT_MASSIVE_KEY", "")
print(f"key length {len(key)} (32 = the real key)")
p = MassiveProvider(["SPY"], api_key=key)

calls = []
_orig_get = p._get
def timed_get(url, params=None):
    t = time.perf_counter()
    body = _orig_get(url, params)
    dt = time.perf_counter() - t
    n = len(body.get("results") or [])
    calls.append((url.split("?")[0].replace(p.base_url, ""), params and dict(params), n, dt, body.get("status"), bool(body.get("next_url"))))
    return body
p._get = timed_get

t = time.perf_counter(); st = p.feed_status(); print("feed_status", st, f"{time.perf_counter()-t:.2f}s", "calls", len(calls))
calls.clear()
t = time.perf_counter(); exps = p.available_expiries("SPY"); dt = time.perf_counter() - t
print(f"available_expiries SPY: {len(exps)} expiries, {len(calls)} pages, rows {sum(c[2] for c in calls)}, {dt:.2f}s; per page: {[round(c[3],2) for c in calls]}")
calls.clear()
near = exps[0]
# page-size clamp test: ask the snapshot for limit=1000 on the nearest expiry
body = timed_get(f"{p.base_url}/v3/snapshot/options/SPY", {"expiration_date": near.isoformat(), "limit": 1000})
print(f"snapshot limit=1000 -> {calls[-1][2]} rows, next_url={calls[-1][5]}, {calls[-1][3]:.2f}s status={calls[-1][4]}")
# same expiry with the app's 250 page
calls.clear()
rows = list(p._paginate("/v3/snapshot/options/SPY", {"expiration_date": near.isoformat(), "limit": _SNAPSHOT_LIMIT}))
print(f"snapshot limit=250 nearest expiry: {len(rows)} rows over {len(calls)} pages, {sum(c[3] for c in calls):.2f}s; per page {[round(c[3],2) for c in calls]}")
# a whole-chain single query with expiration_date.lte, one page: how many rows per page and latency
calls.clear()
body = timed_get(f"{p.base_url}/v3/snapshot/options/SPY", {"expiration_date.lte": exps[-1].isoformat(), "limit": 250})
print(f"whole-chain first page: {calls[-1][2]} rows, {calls[-1][3]:.2f}s, next_url={calls[-1][5]}")
# response headers: rate-limit / retry hints (names only + values of X-RateLimit if any)
import httpx
with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=15.0) as c:
    r = c.get(f"{p.base_url}/v3/reference/options/contracts", params={"underlying_ticker": "SPY", "limit": 1})
    hdrs = {k: v for k, v in r.headers.items() if k.lower() in ("x-ratelimit-limit", "x-ratelimit-remaining", "retry-after", "ratelimit-limit", "ratelimit-remaining", "content-encoding", "server", "x-request-id")}
    print("http", r.status_code, r.http_version, "headers:", hdrs, "all header names:", sorted(r.headers.keys()))
    # HTTP/2 support probe
try:
    with httpx.Client(http2=True, headers={"Authorization": f"Bearer {key}"}, timeout=15.0) as c2:
        r2 = c2.get(f"{p.base_url}/v3/reference/options/contracts", params={"underlying_ticker": "SPY", "limit": 1})
        print("http2 client ->", r2.http_version)
except Exception as exc:
    print("http2 probe failed:", type(exc).__name__, str(exc)[:80])
p.close()
