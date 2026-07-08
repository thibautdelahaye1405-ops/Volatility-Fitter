"""Stage the LIVE market session for the deck's market-facing screenshots.

Target: the single-origin app served by ``backend\\desktop.py`` in server mode
(VOLFIT_DESKTOP_MODE=server VOLFIT_DESKTOP_PORT=8001 VOLFIT_PROVIDER=yahoo,
plus a scratch VOLFIT_DB). Usage:

    python Docs\\deck\\stage_market.py [http://127.0.0.1:8001]

Steps (idempotent — safe to rerun):
  1. wait for the server
  2. force the universe to exactly SPY QQQ AAPL NVDA IWM
  3. restrict each ticker to ~6 expiries nearest 30/60/90/180/365/540 days
  4. install the SPY event calendar (two events, per Docs/deck/README.md)
  5. fetch spots + option chains
  6. calibrate everything and poll to idle, printing progress

Stdlib only (urllib), no dependencies.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001").rstrip("/")

TICKERS = ["SPY", "QQQ", "AAPL", "NVDA", "IWM"]
TARGET_DAYS = [30, 60, 90, 180, 365, 540]
SPY_EVENTS = [{"time": 0.12, "weight": 3, "label": ""}, {"time": 0.37, "weight": 3, "label": ""}]

CALIBRATION_TIMEOUT_S = 45 * 60  # cold live Yahoo 30-node session ~2 min; huge margin


def log(msg: str) -> None:
    print(f"[stage_market] {msg}", flush=True)


def req(method: str, path: str, body=None, timeout: float = 120.0):
    """One JSON request; raises RuntimeError with the server detail on non-2xx."""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"{method} {path} -> {e}") from None


def wait_server(timeout_s: float = 180.0) -> None:
    log(f"waiting for server at {BASE} ...")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            uni = req("GET", "/universe", timeout=15)
            log(f"server up — universe: {uni['tickers']}")
            return
        except Exception:
            time.sleep(2.0)
    raise SystemExit(f"FATAL: server at {BASE} did not come up within {timeout_s:.0f}s")


def ensure_universe() -> None:
    """Add the deck tickers, then remove everything else (adds first, so the
    'cannot remove last ticker' guard never trips)."""
    current = req("GET", "/universe")["tickers"]
    for t in TICKERS:
        if t not in current:
            log(f"adding {t} to the universe")
            req("POST", "/universe/tickers", {"symbol": t}, timeout=180)
    current = req("GET", "/universe")["tickers"]
    for t in current:
        if t not in TICKERS:
            log(f"removing extra ticker {t}")
            req("DELETE", f"/universe/tickers/{t}", timeout=60)
    final = req("GET", "/universe")["tickers"]
    log(f"universe now: {final}")
    missing = [t for t in TICKERS if t not in final]
    if missing:
        raise SystemExit(f"FATAL: tickers missing after staging: {missing}")


def restrict_expiries() -> None:
    """Per ticker: keep the ~6 listed expiries nearest 30/60/90/180/365/540d."""
    for t in TICKERS:
        picker = req("GET", f"/universe/{t}/expiries", timeout=180)
        options = [o for o in picker["expiries"] if o["days"] > 5]
        if not options:
            raise SystemExit(f"FATAL: {t} lists no usable expiries: {picker}")
        chosen: list[str] = []
        for target in TARGET_DAYS:
            best = min(options, key=lambda o: abs(o["days"] - target))
            if best["expiry"] not in chosen:
                chosen.append(best["expiry"])
        chosen.sort()
        res = req("PUT", f"/universe/{t}/expiries", {"expiries": chosen}, timeout=60)
        days = [o["days"] for o in res["expiries"] if o["selected"]]
        log(f"{t}: selected {len(chosen)} expiries (days to expiry: {days})")


def stage_events() -> None:
    cal = req("PUT", "/events/SPY", {"events": SPY_EVENTS})
    log(f"SPY event calendar staged: {cal['events']}")


def stage_options() -> None:
    """Force the market-session settings: Local-Vol calibration ON (the Local
    Vol shots need it) and the observation filter OFF (no FILTER badge on the
    market shots) — in case the scratch DB was reused from a graph session."""
    opts = req("GET", "/settings/options")
    changed = opts["localVolEnabled"] is not True or opts["observationFilterMode"] != "off"
    opts["localVolEnabled"] = True
    opts["observationFilterMode"] = "off"
    req("PUT", "/settings/options", opts)
    log(f"options staged: localVolEnabled=True, observationFilterMode=off (changed: {changed})")


def fetch_market_data() -> bool:
    log("fetching spots ...")
    spots = req("POST", "/fetch/spots", {}, timeout=300)
    for t, s in sorted(spots.items()):
        log(f"  spot {t}: {s.get('price', s)}")
    log("fetching option chains (can take a minute on live Yahoo) ...")
    res = req("POST", "/fetch/options", {}, timeout=1800)
    log(f"chains fetched for {res['tickers']} (auto-calibrate started: {res['calibrationStarted']})")
    return bool(res["calibrationStarted"])


def wait_calibration_idle(timeout_s: float = CALIBRATION_TIMEOUT_S) -> dict:
    """Poll GET /calibration/status until the background job is idle."""
    deadline = time.monotonic() + timeout_s
    last_line = ""
    # Give the background job a moment to flip to running before the first poll.
    time.sleep(1.5)
    while time.monotonic() < deadline:
        st = req("GET", "/calibration/status", timeout=30)
        line = (
            f"running={st['running']} {st['done']}/{st['total']} "
            f"current='{st['current']}' phase='{st['phase']}' stale={st['staleNodes']}"
        )
        if line != last_line:
            log(f"  calibration: {line}")
            last_line = line
        if not st["running"]:
            if st["error"]:
                log(f"  WARNING: last per-node calibration error: {st['error']}")
            return st
        time.sleep(2.0)
    raise SystemExit(f"FATAL: calibration did not finish within {timeout_s:.0f}s")


def calibrate_all() -> dict:
    req("POST", "/calibrate", timeout=60)
    return wait_calibration_idle()


def main() -> None:
    wait_server()
    ensure_universe()
    restrict_expiries()
    stage_events()
    stage_options()
    started = fetch_market_data()
    if started:
        log("waiting for the auto-calibration to finish ...")
        wait_calibration_idle()
    log("triggering a full calibration (idempotent — refits anything stale) ...")
    st = calibrate_all()
    if st["staleNodes"] > 0:
        log(f"{st['staleNodes']} nodes still stale — one more calibration pass")
        st = calibrate_all()
    log(
        f"DONE — lit nodes: {st['litNodes']}, stale: {st['staleNodes']}, "
        f"epoch: {st['epoch']}. Ready for capture_market.mjs."
    )


if __name__ == "__main__":
    main()
