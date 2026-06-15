"""Massive/Polygon feed diagnostic — run with your key to pinpoint why a chain
won't load (e.g. the '0 expiries' symptom on an entitled plan).

Usage (repo root, venv active):
    $env:VOLFIT_MASSIVE_KEY="...."            # PowerShell
    .venv\\Scripts\\python backend\\massive_diag.py SPY

It probes BOTH hosts (api.massive.com and api.polygon.io) and, for each, walks
the exact calls the provider makes — contracts reference, the option-chain
snapshot (reporting which fields are present: last_quote bid/ask, day.close,
implied_volatility, underlying_asset.price, exercise style), then the real
``fetch_chain`` and the spot resolution — printing where (and why) it fails.
Share the output and we can fix the precise cause. Read-only; no app state.
"""

from __future__ import annotations

import os
import sys
from datetime import date

HOSTS = ["https://api.massive.com", "https://api.polygon.io"]


def _http_get(api_key: str):
    import httpx

    def get(url: str, params: dict | None) -> dict:
        r = httpx.get(
            url, params=params,
            headers={"Authorization": f"Bearer {api_key}"}, timeout=20.0,
        )
        try:
            body = r.json()
        except Exception:
            body = {"_status_code": r.status_code, "_text": r.text[:200]}
        body.setdefault("_status_code", r.status_code)
        return body

    return get


def _present(v) -> str:
    return "—" if v is None else repr(v)


def probe_host(host: str, ticker: str, api_key: str) -> None:
    from volfit.data.massive import MassiveProvider

    print(f"\n{'=' * 70}\nHOST {host}\n{'=' * 70}")
    get = _http_get(api_key)
    prov = MassiveProvider([ticker], api_key=api_key, base_url=host, http_get=get)

    # 1. contracts reference (entitled on every tier)
    ref = get(f"{host}/v3/reference/options/contracts",
              {"underlying_ticker": ticker.upper(), "limit": 3})
    print(f"[contracts] HTTP {ref.get('_status_code')} status={ref.get('status')} "
          f"results={len(ref.get('results') or [])} msg={ref.get('message','')}")
    if ref.get("results"):
        c = ref["results"][0]
        print(f"            sample: ticker={c.get('ticker')} expiry={c.get('expiration_date')} "
              f"strike={c.get('strike_price')} type={c.get('contract_type')} style={c.get('exercise_style')}")

    # 2. option-chain snapshot (NBBO + IV + underlying price live here)
    snap = get(f"{host}/v3/snapshot/options/{ticker.upper()}", {"limit": 3})
    res = snap.get("results") or []
    print(f"[snapshot ] HTTP {snap.get('_status_code')} status={snap.get('status')} "
          f"results={len(res)} msg={snap.get('message','')}")
    if res:
        r0 = res[0]
        lq = r0.get("last_quote") or {}
        ua = r0.get("underlying_asset") or {}
        day = r0.get("day") or {}
        print(f"            last_quote.bid={_present(lq.get('bid'))} ask={_present(lq.get('ask'))} "
              f"midpoint={_present(lq.get('midpoint'))}")
        print(f"            day.close={_present(day.get('close'))} "
              f"implied_volatility={_present(r0.get('implied_volatility'))}")
        print(f"            underlying_asset.price={_present(ua.get('price'))}  "
              f"(this is the spot the chain prefers)")
        print(f"            result keys: {sorted(r0.keys())}")

    # 3. available_expiries + fetch_chain through the provider
    try:
        exps = prov.available_expiries(ticker)
        print(f"[expiries ] available_expiries -> {len(exps)}: {[e.isoformat() for e in exps[:4]]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[expiries ] FAILED: {type(exc).__name__}: {exc}")
        exps = []

    if exps:
        near = exps[0]
        try:
            chain = prov.fetch_chain(ticker, [near])
            two = sum(1 for q in chain.quotes if q.bid is not None and q.ask is not None)
            print(f"[chain    ] fetch_chain({near}) -> spot={chain.spot} "
                  f"quotes={len(chain.quotes)} two_sided={two} style={chain.exercise_style}")
        except Exception as exc:  # noqa: BLE001
            print(f"[chain    ] fetch_chain FAILED: {type(exc).__name__}: {exc}")

    # 4. the STOCKS-snapshot spot fallback (a SEPARATE plan from options)
    try:
        spot = prov._spot(ticker)
        print(f"[stk spot ] stocks-snapshot spot -> {spot} (stocks plan IS entitled)")
    except Exception as exc:  # noqa: BLE001
        print(f"[stk spot ] stocks-snapshot spot FAILED: {type(exc).__name__}: {exc}")
        print("            ^ expected if you have OPTIONS but not STOCKS; the provider")
        print("              now derives spot from option parity instead, so this is OK.")


def main() -> int:
    api_key = os.environ.get("VOLFIT_MASSIVE_KEY", "").strip()
    if not api_key:
        print("Set VOLFIT_MASSIVE_KEY first.")
        return 2
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "SPY").upper()
    print(f"Massive diagnostic — ticker {ticker}, key ...{api_key[-4:]}, {date.today()}")
    for host in HOSTS:
        try:
            probe_host(host, ticker, api_key)
        except Exception as exc:  # noqa: BLE001
            print(f"\nHOST {host} probe crashed: {type(exc).__name__}: {exc}")
    print("\nDone. Share this output to pin down the exact gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
