"""Stage the demo desk on the private :8011 server: monthly ladders, fetch, options, calibrate, priors."""
import json, time, sys
import httpx

B = "http://127.0.0.1:8011"
c = httpx.Client(base_url=B, timeout=600)

def pick(ticker):
    d = c.get(f"/universe/{ticker}/expiries").json()
    rows = d["expiries"]
    keep = [r["expiry"] for r in rows if r["bucket"] in ("monthly", "quarterly") and 14 <= r["days"] <= 380]
    # two near weeklies for the front of the ladder (SPY / QQQ only)
    if ticker in ("SPY", "QQQ"):
        wk = [r["expiry"] for r in rows if r["bucket"] == "weekly" and 5 <= r["days"] <= 40]
        keep = sorted(set(keep + wk[:2]))
    keep = sorted(keep)[:10]
    r = c.put(f"/universe/{ticker}/expiries", json={"expiries": keep})
    r.raise_for_status()
    print(ticker, len(keep), keep)

for t in c.get("/universe").json()["tickers"]:
    pick(t)

t0 = time.time()
r = c.post("/fetch/snapshot", json={})
print("fetch", r.status_code, round(time.time() - t0, 1), "s", json.dumps(r.json())[:400])
print("errors", c.get("/universe").json().get("errors"))

opt = c.get("/settings/options").json()
opt.update({
    "fitMode": "haircut",
    "priorPersistenceMode": "hybrid",
    "observationFilterMode": "overlay",
    "graphPropagationMode": "layered_dynamic_harmonic",
    "autoCalibrate": False,
    "eventsEnabled": True,
    "varSwapEnabled": True,
    "localVolEnabled": True,
})
r = c.put("/settings/options", json=opt)
print("options", r.status_code, {k: r.json().get(k) for k in ("fitMode", "priorPersistenceMode", "observationFilterMode", "graphPropagationMode", "dynamicsRegime", "ssr", "timeScheme", "lvLattice", "lvSolver")})

t0 = time.time()
r = c.post("/calibrate", params={"fit_mode": "haircut"})
print("calibrate started", r.status_code)
while True:
    st = c.get("/calibration/status", params={"fit_mode": "haircut"}).json()
    if not st["running"]:
        break
    time.sleep(0.5)
print("calibrated in", round(time.time() - t0, 1), "s", {k: st[k] for k in ("total", "done", "error", "litNodes", "staleNodes", "lvStaleTickers")})

r = c.post("/priors/save-all", params={"fitMode": "haircut"})
print("priors", r.status_code, json.dumps(r.json())[:300])
r = c.post("/universes/demo-core")
print("saved universe", r.status_code)
q = c.get("/quality", params={"fit_mode": "haircut"}).json()
print("quality keys", list(q.keys())[:12])
print(json.dumps({k: q[k] for k in q if k not in ("nodes", "tickers")})[:800])
