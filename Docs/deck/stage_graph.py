"""Stage the SYNTHETIC graph + observation-filter demo for the deck shots.

Target: the single-origin app served by ``backend\\desktop.py`` in server mode
with VOLFIT_PROVIDER=synthetic and a SCRATCH VOLFIT_DB (never the user's), e.g.

    $env:VOLFIT_DESKTOP_MODE='server'; $env:VOLFIT_DESKTOP_PORT='8001'
    $env:VOLFIT_PROVIDER='synthetic'; $env:VOLFIT_DB='...\\deck_graph.sqlite'
    $env:VOLFIT_TICKERS='SPY,QQQ,AAPL,NVDA,IWM'   # optional; staged anyway
    .venv\\Scripts\\python backend\\desktop.py

Usage:  python Docs\\deck\\stage_graph.py [http://127.0.0.1:8001]

Recipe (Docs/deck/README.md steps 1-3 + 5), idempotent:
  1. universe = SPY QQQ AAPL NVDA IWM, everything LIT (rerun-safe)
  2. options: observation filter ACTIVE, graph-prior defaults eta 3.16 /
     lambda 0.1 / nu 0.1 (these seed the Graph tab's Solver panel), LV off
     (not needed for graph shots — keeps the three calibrations fast)
  3. fetch spots + options; calibrate #0 (seeds the filter state + baselines)
  4. save priors, then FETCH priors (activates them — without the fetch the
     extrapolation falls back to today_bootstrap and every innovation is 0)
  5. darken QQQ / AAPL / NVDA / IWM
  6. amend EVERY SPY quote mid +150 bp; calibrate #1 (the big lit innovation)
  7. nudge one near-ATM SPY quote +10 bp more; calibrate #2 (a realistic
     small innovation so the filter overlay / gains table look sensible)
  8. POST /graph/extrapolate with the deck knobs (eta 3.16, kappa 1,
     lambda 0.1, nu 0.1, cross-ticker edge weight 30) and PRINT the per-node
     shifts/bands + the NVDA hero-node reconstruction metrics + the SPY
     filter diagnostics — the numbers the slide captions cite.

NOTE: the capture script must still set the cross-ticker edge weight (30) in
the UI Solver panel — edge weights are UI state, only eta/kappa/lambda/nu are
seeded from the Options graph-prior defaults. capture_graph.mjs does this.

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
DARK_TICKERS = ["QQQ", "AAPL", "NVDA", "IWM"]
SHIFT_VOL = 0.0150   # +150 bp on every SPY quote mid
NUDGE_VOL = 0.0010   # +10 bp second-pass nudge for the filter story

#: Solver knobs of the deck's propagation (README step 3: eta 3.16x = slider
#: 0.5, lambda 0.1, cross-ticker weight 30). Must match capture_graph.mjs.
KNOBS = {
    "etaScale": 3.16,
    "kappaScale": 1.0,
    "lambdaScale": 0.1,
    "nu": 0.1,
    "crossWeight": 30.0,
    "flatAtm": False,
}

CALIBRATION_TIMEOUT_S = 30 * 60


def log(msg: str) -> None:
    print(f"[stage_graph] {msg}", flush=True)


def req(method: str, path: str, body=None, timeout: float = 120.0):
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


def wait_calibration_idle(timeout_s: float = CALIBRATION_TIMEOUT_S) -> dict:
    deadline = time.monotonic() + timeout_s
    last_line = ""
    time.sleep(1.5)
    while time.monotonic() < deadline:
        st = req("GET", "/calibration/status", timeout=30)
        line = (
            f"running={st['running']} {st['done']}/{st['total']} "
            f"current='{st['current']}' stale={st['staleNodes']}"
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


def calibrate(tag: str) -> dict:
    log(f"calibrating ({tag}) ...")
    req("POST", "/calibrate", timeout=60)
    return wait_calibration_idle()


def ensure_universe() -> None:
    current = req("GET", "/universe")["tickers"]
    for t in TICKERS:
        if t not in current:
            log(f"adding {t} to the universe")
            req("POST", "/universe/tickers", {"symbol": t}, timeout=120)
    current = req("GET", "/universe")["tickers"]
    for t in current:
        if t not in TICKERS:
            log(f"removing extra ticker {t}")
            req("DELETE", f"/universe/tickers/{t}", timeout=60)
    log(f"universe now: {req('GET', '/universe')['tickers']}")
    # Rerun-safety: a previous run darkened four tickers; re-light everything so
    # the full calibration + prior save cover the whole universe again.
    for t in TICKERS:
        req("PUT", f"/universe/lit/{t}", {"lit": True})
    log("all nodes re-lit")


def stage_options(filter_mode: str = "off") -> None:
    """Graph-prior defaults (seed the UI Solver panel) + LV off.

    The observation filter starts OFF: an active filter during calibration #1
    MAP-damps the +150 bp repricing (the committed fit shrinks toward the
    transported prediction), which mutes the lit innovations the graph story
    depends on. It is switched to ACTIVE only after the extrapolation, for the
    filter shots."""
    opts = req("GET", "/settings/options")
    opts["observationFilterMode"] = filter_mode
    opts["graphEtaScale"] = KNOBS["etaScale"]
    opts["graphKappaScale"] = KNOBS["kappaScale"]
    opts["graphLambdaScale"] = KNOBS["lambdaScale"]
    opts["graphNu"] = KNOBS["nu"]
    opts["localVolEnabled"] = False  # graph shots don't need LV; 3x faster staging
    res = req("PUT", "/settings/options", opts)
    log(
        "options staged: filter="
        f"{res['observationFilterMode']}, graph eta/kappa/lambda/nu = "
        f"{res['graphEtaScale']}/{res['graphKappaScale']}/"
        f"{res['graphLambdaScale']}/{res['graphNu']}, LV={res['localVolEnabled']}"
    )


def fetch_market_data() -> None:
    log("fetching spots + options (synthetic — fast) ...")
    req("POST", "/fetch/spots", {}, timeout=120)
    res = req("POST", "/fetch/options", {}, timeout=600)
    log(f"chains fetched for {res['tickers']} (auto-calibrate: {res['calibrationStarted']})")
    if res["calibrationStarted"]:
        wait_calibration_idle()


def stage_priors() -> None:
    saved = req("POST", "/priors/save-all?fitMode=mid", {}, timeout=600)
    log(f"priors saved: {json.dumps(saved)}")
    fetched = req("POST", "/priors/fetch?fitMode=mid", {}, timeout=600)
    log(f"priors FETCHED (activated): {json.dumps(fetched)}")


def darken_targets() -> None:
    for t in DARK_TICKERS:
        req("PUT", f"/universe/lit/{t}", {"lit": False})
    log(f"darkened: {DARK_TICKERS} (SPY stays lit)")


def spy_expiries() -> list[str]:
    uni = req("GET", "/universe")
    exps = [e["expiry"] for e in uni["expiries"]["SPY"]]
    if not exps:
        raise SystemExit("FATAL: SPY has no expiries in the universe payload")
    return exps


def amend_spy(shift: float) -> None:
    """Bulk-amend every included SPY quote's mid IV by +shift (per expiry).

    Resets each expiry's edit session first, so a RERUN of this script shifts
    from the market mids again instead of stacking +150 bp on +150 bp."""
    for expiry in spy_expiries():
        try:
            req("POST", f"/smiles/SPY/{expiry}/edits?fit_mode=mid", {"action": "reset"}, timeout=180)
        except RuntimeError as e:  # a fresh node may have no edit session yet
            log(f"  (reset skipped on SPY {expiry}: {e})")
        smile = req("GET", f"/smiles/SPY/{expiry}")
        n = 0
        for q in smile["quotes"]:
            if q["excluded"]:
                continue
            req(
                "POST",
                f"/smiles/SPY/{expiry}/edits?fit_mode=mid",
                {"action": "amend", "index": q["index"], "mid": q["mid"] + shift},
                timeout=180,
            )
            n += 1
        log(f"  SPY {expiry}: amended {n} quote mids by {shift * 1e4:+.0f} bp")


def nudge_spy_atm(shift: float) -> str:
    """Amend the single nearest-ATM quote of a mid SPY expiry by +shift."""
    exps = spy_expiries()
    expiry = exps[len(exps) // 2]
    smile = req("GET", f"/smiles/SPY/{expiry}")
    quotes = [q for q in smile["quotes"] if not q["excluded"]]
    q = min(quotes, key=lambda q: abs(q["k"]))
    req(
        "POST",
        f"/smiles/SPY/{expiry}/edits?fit_mode=mid",
        {"action": "amend", "index": q["index"], "mid": q["mid"] + shift},
        timeout=180,
    )
    log(f"  nudged SPY {expiry} k={q['k']:+.3f} by {shift * 1e4:+.0f} bp")
    return expiry


def run_extrapolation() -> None:
    """POST /graph/extrapolate with the deck knobs; print the caption numbers."""
    log(f"extrapolating with knobs {KNOBS} (first call builds the graph universe) ...")
    res = req("POST", "/graph/extrapolate", KNOBS, timeout=1800)
    nodes = res["nodes"]

    log("=" * 78)
    log("PER-NODE EXTRAPOLATION (prior -> posterior ATM, for the slide captions):")
    for n in sorted(nodes, key=lambda n: (n["ticker"], n["expiry"])):
        band_bp = (n["bandHi"] - n["bandLo"]) / 2 * 1e4
        innov = f" innov {n['innovationBp']:+.1f}bp" if n["innovationBp"] is not None else ""
        log(
            f"  {n['ticker']:<5} {n['expiry']}  {'LIT ' if n['lit'] else 'dark'} "
            f"prior {n['priorAtmVol'] * 100:6.2f}% -> post {n['postAtmVol'] * 100:6.2f}%  "
            f"shift {n['shiftBp']:+7.1f} bp  band ±{band_bp:5.0f} bp  "
            f"[{n['priorSource']}]{innov}"
        )
    for t in DARK_TICKERS:
        dark = [n for n in nodes if n["ticker"] == t and not n["lit"]]
        if dark:
            mean_shift = sum(n["shiftBp"] for n in dark) / len(dark)
            mean_band = sum((n["bandHi"] - n["bandLo"]) / 2 * 1e4 for n in dark) / len(dark)
            log(f"  {t}: mean dark shift {mean_shift:+.1f} bp inside ±{mean_band:.0f} bp band")

    # NVDA hero node: the reconstructed smile the smile_hero shot drills into.
    nvda_dark = sorted(
        (n for n in nodes if n["ticker"] == "NVDA" and not n["lit"]),
        key=lambda n: n["expiry"],
    )
    if not nvda_dark:
        log("WARNING: no dark NVDA nodes — smile_hero staging is off")
        return
    hero = nvda_dark[len(nvda_dark) // 2]
    query = "&".join(
        f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in KNOBS.items()
    )
    smile = req(
        "GET", f"/graph/extrapolate/nodes/NVDA/{hero['expiry']}?{query}", timeout=600
    )
    log("=" * 78)
    log(f"HERO NODE NVDA {hero['expiry']} (smile_hero caption numbers):")
    log(
        f"  prior ATM {smile['priorAtmVol'] * 100:.2f}% -> post {smile['postAtmVol'] * 100:.2f}% "
        f"(shift {(smile['postAtmVol'] - smile['priorAtmVol']) * 1e4:+.1f} bp, sd {smile['sd'] * 1e4:.0f} bp)"
    )
    m = smile.get("metrics")
    if m:
        zeta = m.get("standardizedResidual")
        log(
            f"  vs market quotes: RMS {m['rmsVol'] * 100:.2f}% vol · "
            f"in-band {m['insideSpreadHitRate'] * 100:.0f}% of {m['nQuotes']} quotes · "
            f"ATM residual {m['atmResidualBp']:+.1f} bp"
            + (f" · zeta {zeta:.2f}" if zeta is not None else "")
        )
    else:
        log("  (no quote metrics on this node)")
    if smile.get("attribution"):
        log("  attribution (gain x innovation):")
        for a in smile["attribution"]:
            log(f"    {a['ticker']} {a['expiry']}: {a.get('contributionBp', 0):+.1f} bp")


def print_filter_diagnostics(nudged_expiry: str) -> None:
    """The filter gains/innovation on the nudged SPY node (filter_panel caption)."""
    try:
        d = req("GET", f"/smiles/SPY/{nudged_expiry}/filter?fit_mode=mid", timeout=120)
    except RuntimeError as e:
        log(f"WARNING: filter diagnostics unavailable: {e}")
        return
    log("=" * 78)
    log(f"FILTER DIAGNOSTICS SPY {nudged_expiry} (filter_smile / filter_panel captions):")
    log(f"  raw: {json.dumps(d)[:600]}")
    if d.get("active"):
        gains = "/".join(f"{g:.2f}" for g in d.get("gain", []))
        innov = d.get("innovation", [None])[0]
        log(
            f"  gains K = {gains}"
            + (f" · ATM innovation {innov * 1e4:+.1f} bp" if innov is not None else "")
            + (f" · contaminated={d.get('contaminated')}")
        )


def main() -> None:
    wait_server()
    ensure_universe()
    stage_options(filter_mode="off")  # filter OFF: full +150 bp innovations
    fetch_market_data()
    calibrate("#0 — baseline")
    stage_priors()
    darken_targets()
    log(f"amending every SPY quote mid by {SHIFT_VOL * 1e4:+.0f} bp ...")
    amend_spy(SHIFT_VOL)
    calibrate("#1 — the +150 bp lit innovation (filter off, undamped)")
    run_extrapolation()
    # --- filter story, staged AFTER the graph numbers are locked in ---------
    log("activating the observation filter for the filter shots ...")
    stage_options(filter_mode="active")
    nudged = nudge_spy_atm(NUDGE_VOL)
    calibrate("#2 — small innovation under the ACTIVE filter (seeds from #1)")
    print_filter_diagnostics(nudged)
    log("DONE — ready for capture_graph.mjs.")


if __name__ == "__main__":
    main()
