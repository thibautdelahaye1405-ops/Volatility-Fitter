"""Re-stage on Nasdaq (fresh delayed bid/ask): source, ladders, fetch, calibrate, priors, universe."""
import json, time
import httpx
B = "http://127.0.0.1:8011"
c = httpx.Client(base_url=B, timeout=900)
print("activate", c.post("/datasource/nasdaq").status_code)
for t in ("SPY", "NVDA", "AAPL", "QQQ", "XOM", "MSFT"):
    r = c.put(f"/universe/{t}/source", json={"source": None}); r.raise_for_status()
def pick(ticker):
    rows = c.get(f"/universe/{ticker}/expiries").json()["expiries"]
    keep = [r["expiry"] for r in rows if r["bucket"] in ("monthly", "quarterly") and 14 <= r["days"] <= 380]
    if ticker in ("SPY", "QQQ"):
        wk = [r["expiry"] for r in rows if r["bucket"] == "weekly" and 5 <= r["days"] <= 40]
        keep = sorted(set(keep + wk[:2]))
    keep = sorted(keep)[:10]
    c.put(f"/universe/{ticker}/expiries", json={"expiries": keep}).raise_for_status()
    print(ticker, len(keep), keep)
tickers = c.get("/universe").json()["tickers"]
for t in tickers: pick(t)
t0 = time.time(); r = c.post("/fetch/snapshot", json={}); dt = time.time() - t0
print("fetch", r.status_code, round(dt, 1), "s", r.json().get("spots"))
u = c.get("/universe").json(); print("errors", u["errors"])
print({t: u["expiries"][t][0]["effectiveAsOf"] for t in tickers})
print("dataAge", c.get("/datasources").json().get("dataAge"))
t0 = time.time(); c.post("/calibrate", params={"fit_mode": "haircut"})
while True:
    st = c.get("/calibration/status", params={"fit_mode": "haircut"}).json()
    if not st["running"]: break
    time.sleep(0.5)
print("calibrated in", round(time.time() - t0, 1), "s", {k: st[k] for k in ("total", "done", "error", "litNodes", "lvStaleTickers")})
print("priors", c.post("/priors/save-all", params={"fitMode": "haircut"}).json())
print("universe saved", c.post("/universes/demo-core").status_code)
q = c.get("/quality", params={"fit_mode": "haircut"}).json()
print(json.dumps(q["summary"]))
for n in q["nodes"]:
    print(n["ticker"], n["expiry"], "n", n["nQuotes"], "rms", round(n["rmsBp"] or 0, 1), "max", round(n["maxIvBp"] or 0), "lee", n["leeLeft"], n["leeRight"], "ready", n["ready"], n["issues"])
