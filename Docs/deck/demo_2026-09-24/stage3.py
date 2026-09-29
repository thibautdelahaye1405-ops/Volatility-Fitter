"""Stage the demo extras: clear stale, events, a var-swap quote, dark nodes, recalibrate."""
import json, time
import httpx
B = "http://127.0.0.1:8011"
c = httpx.Client(base_url=B, timeout=900)
FM = {"fit_mode": "haircut"}

def calibrate(label):
    t0 = time.time(); c.post("/calibrate", params=FM)
    while True:
        st = c.get("/calibration/status", params=FM).json()
        if not st["running"]: break
        time.sleep(0.5)
    print(label, "calibrated in", round(time.time() - t0, 1), "s", st["error"] or "ok")

# 1. events: auto-calibrate three names whose Q3 prints fall inside the Oct-16 -> Nov-20 interval
for t in ("AAPL", "MSFT", "NVDA"):
    r = c.post(f"/events/{t}/autocalibrate", json={"maxExpiry": "2027-01-15", "fitMode": "haircut"})
    print("events", t, r.status_code, json.dumps(r.json())[:400])

# 2. a var-swap quote on QQQ Dec-18 at the model level + 0.6 vol pt
sm = c.get("/smiles/QQQ/2026-12-18", params=FM).json()
vs = sm.get("varSwap") or {}
print("QQQ Dec varswap before", {k: vs.get(k) for k in ("level", "modelVol", "enabled", "weightPct")})
if vs.get("modelVol"):
    r = c.post("/smiles/QQQ/2026-12-18/varswap", params=FM, json={"action": "set", "level": round(vs["modelVol"] + 0.006, 4)})
    print("varswap set", r.status_code, {k: (r.json().get("varSwap") or {}).get(k) for k in ("level", "modelVol")})

# 3. dark nodes for the graph demo (each has quotes -> scorable)
DARK = [("AAPL", "2027-02-19"), ("AAPL", "2027-04-16"), ("MSFT", "2027-03-19"), ("MSFT", "2027-04-16"),
        ("NVDA", "2027-02-19"), ("NVDA", "2027-04-16"), ("XOM", "2027-04-16"), ("XOM", "2026-11-20")]
for t, e in DARK:
    r = c.put(f"/universe/lit/{t}/{e}", json={"lit": False}); print("dark", t, e, r.status_code)

# 4. recalibrate so nothing is stale, save the universe with its marks
calibrate("final")
print("universe saved", c.post("/universes/demo-core").status_code)
q = c.get("/quality", params=FM).json(); print(json.dumps(q["summary"]))
ev = c.get("/events/AAPL").json(); print("AAPL events", json.dumps(ev)[:300])
pf = c.post("/graph/preflight", json={}); print("preflight", pf.status_code, json.dumps(pf.json())[:400])
