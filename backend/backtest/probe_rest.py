"""Probe the per-contract REST-quotes path as a firehose alternative (ROADMAP).

The flat-file `quotes_v1` firehose costs ~4.8 h/day. The alternative: enumerate a
day's option contracts (`/v3/reference/options/contracts?as_of=`) then fetch each
contract's NBBO at the 15:45-ET instant via `/v3/quotes/{O:..}?timestamp.lte=&
order=desc&limit=1`. This probe answers the make-or-break questions, read-only:

  1. does HISTORICAL /v3/quotes work on our key for Aug-2024 (entitlement+lookback)?
  2. the RATE LIMIT (a 5/min basic tier would be slower than the firehose);
  3. per-call latency;
  4. contract enumeration as-of a past date (incl. an index, I:SPX).

Run with the REST key in env: $env:VOLFIT_MASSIVE_KEY=...  (dot-source restart.local.ps1).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx

KEY = os.environ.get("VOLFIT_MASSIVE_KEY", "").strip()
HOSTS = ["https://api.polygon.io", "https://api.massive.com"]
TS_NS = int(datetime(2024, 8, 5, 19, 45, 0, tzinfo=timezone.utc).timestamp() * 1e9)
HDRS = {"Authorization": f"Bearer {KEY}"}


def _get(host: str, path: str, params: dict) -> tuple[int, dict, dict]:
    r = httpx.get(host + path, params=params, headers=HDRS, timeout=30.0)
    try:
        body = r.json()
    except Exception:
        body = {"_text": r.text[:200]}
    return r.status_code, body, dict(r.headers)


def _ratelimit(headers: dict) -> str:
    keys = {k.lower(): v for k, v in headers.items()}
    bits = [f"{k}={keys[k]}" for k in keys if "ratelimit" in k or "retry-after" in k]
    return ", ".join(bits) or "(no rate-limit headers)"


def probe(host: str, underlying: str) -> None:
    print(f"\n=== {host}  underlying={underlying} ===")
    # 1. contracts reference, as-of the past date
    sc, body, hdr = _get(host, "/v3/reference/options/contracts",
                         {"underlying_ticker": underlying, "as_of": "2024-08-05",
                          "expiration_date": "2024-08-16", "limit": 250})
    res = body.get("results") or []
    print(f"[contracts] HTTP {sc} status={body.get('status')} n={len(res)} "
          f"next={'yes' if body.get('next_url') else 'no'} msg={body.get('message','')}")
    if not res:
        print(f"           rate-limit: {_ratelimit(hdr)}")
        return
    sample = res[0]["ticker"]
    print(f"           sample contract: {sample}")

    # 2. historical NBBO at the 15:45-ET instant for one contract
    sc, body, hdr = _get(host, f"/v3/quotes/{sample}",
                         {"timestamp.lte": TS_NS, "order": "desc",
                          "sort": "timestamp", "limit": 1})
    q = (body.get("results") or [{}])
    q0 = q[0] if q else {}
    print(f"[quote   ] HTTP {sc} status={body.get('status')} "
          f"bid={q0.get('bid_price')} ask={q0.get('ask_price')} "
          f"ts={q0.get('sip_timestamp')} msg={body.get('message','')}")
    print(f"           rate-limit: {_ratelimit(hdr)}")

    # 3. latency + rate-limit: fire 12 rapid quote calls on the day's contracts
    n = min(12, len(res))
    lat = []
    n429 = 0
    t0 = time.perf_counter()
    for c in res[:n]:
        t = time.perf_counter()
        sc, _b, _h = _get(host, f"/v3/quotes/{c['ticker']}",
                          {"timestamp.lte": TS_NS, "order": "desc", "limit": 1})
        lat.append(time.perf_counter() - t)
        if sc == 429:
            n429 += 1
    wall = time.perf_counter() - t0
    lat.sort()
    print(f"[burst   ] {n} calls in {wall:.1f}s  median={lat[n // 2] * 1e3:.0f}ms  "
          f"max={lat[-1] * 1e3:.0f}ms  429s={n429}")


def main() -> int:
    if not KEY:
        print("Set VOLFIT_MASSIVE_KEY (dot-source restart.local.ps1).")
        return 2
    print(f"REST quotes probe — key ...{KEY[-4:]}, ts=2024-08-05 15:45 ET")
    for host in HOSTS:
        for underlying in ("AAPL", "I:SPX"):
            try:
                probe(host, underlying)
            except Exception as exc:  # noqa: BLE001
                print(f"\n=== {host} {underlying} CRASHED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
