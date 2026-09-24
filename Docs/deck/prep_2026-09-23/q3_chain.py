"""Q3 (speed): FULL-CHAIN timings on the Massive live SPY chain (9 rungs,
q3_chains.pkl). Models LQD-24 / SVI-JW x the calendar switch
(OptionsSettings.enforceCalendar, default True, with surfaceSolver "symmetric"
default; "sequential" = the legacy coupled floor; False = independent warm-
started fits) through the Calibrate button's own item chain
(volfit.api.workflow_stages._parametric_items), SERIAL (VOLFIT_CALIB_WORKERS=1)
then POOLED (8 workers: the Calibrate-job shape = items sequential through the
pool; the POST /fit/surface shape = phase A fanned out over the pool). Then the
LV (affine) surface of the ladder (cold, cold-start JIT-warm x3, warm-started),
and once with enforceCalendar off to show LV ignores the switch.

Run from backend\ :  ..\.venv\Scripts\python <this file>
"""
from __future__ import annotations

import json
import os
import statistics
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["VOLFIT_CALIB_WORKERS"] = "1"

from volfit.api import affine_fit, fit_pool, service, workflow, workflow_stages  # noqa: E402
from volfit.api.schemas import FitSettings, OptionsSettings  # noqa: E402
from volfit.api.schemas_affine import AffineFitRequest  # noqa: E402
from volfit.api.state import AppState  # noqa: E402
from volfit.calib.fit_task import SliceFitTask  # noqa: E402
from volfit.replay_report import _StoredChains  # noqa: E402

TICKER = "SPY"


def load():
    import pickle

    with open(os.path.join(HERE, "q3_chains.pkl"), "rb") as fh:
        data = pickle.load(fh)
    return data["chains"]["massive_live"], data["ladder"], data["today"]


def new_state(chain, ladder, today, model: str, enforce: bool, solver: str = "symmetric") -> AppState:
    st = AppState(today, provider=_StoredChains({TICKER: chain}))
    st.set_expiries(TICKER, ladder)
    st.set_fit_settings(FitSettings(model=model, nOrder=24))
    st.set_options(OptionsSettings(enforceCalendar=enforce, surfaceSolver=solver))
    service.surface_inputs(st, TICKER, "mid")  # forwards + de-Am prep, memoized (timed separately)
    return st


def parametric_serial(st: AppState) -> float:
    nodes = workflow_stages.lit_nodes(st, [TICKER])
    items = workflow_stages._parametric_items(st, nodes, "mid")
    t0 = time.perf_counter()
    for _label, _phase, thunk in items:
        thunk()
    return (time.perf_counter() - t0) * 1e3


def surface_quality(st: AppState) -> dict:
    rms = service.surface_rms_error(st, TICKER, "mid") * 1e4
    per = []
    for e in sorted(st.forwards(TICKER)):
        rec = service.fit_or_get(st, TICKER, e.isoformat(), "mid")
        per.append(round(service.weighted_rms_error(st, TICKER, e.isoformat(), rec, "mid") * 1e4, 1))
    return {"surface_rms_bp": round(rms, 2), "per_expiry_rms_bp": per}


def main() -> None:
    chain, ladder, today = load()
    out: dict = {"ladder": [e.isoformat() for e in ladder], "n_quotes_chain": len(chain.quotes)}

    # ---- the shared prep of the ladder (forwards + de-Am of all 9 rungs), warm
    st = new_state(chain, ladder, today, "lqd", True)
    walls = []
    for _ in range(3):
        s = AppState(today, provider=_StoredChains({TICKER: chain}))
        s.set_expiries(TICKER, ladder)
        t0 = time.perf_counter()
        plan = service.surface_inputs(s, TICKER, "mid")
        walls.append((time.perf_counter() - t0) * 1e3)
    out["surface_inputs_9_rungs_warm_ms"] = {"median": round(statistics.median(walls), 1),
                                             "walls": [round(x, 1) for x in walls],
                                             "fit_quotes_per_rung": [int(p.k.size) for _, p in plan]}

    configs = [
        ("lqd24", True, "symmetric"), ("lqd24", False, "symmetric"), ("lqd24", True, "sequential"),
        ("svi", True, "symmetric"), ("svi", False, "symmetric"),
    ]
    rows = []
    first = True
    for model, enforce, solver in configs:
        m = "lqd" if model == "lqd24" else model
        row = {"model": model, "enforceCalendar": enforce, "surfaceSolver": solver}
        if first:  # the cold run of the process (Numba cache loads + JIT)
            row["serial_cold_ms"] = round(parametric_serial(new_state(chain, ladder, today, m, enforce, solver)), 1)
            first = False
        walls = []
        for _ in range(3):
            st = new_state(chain, ladder, today, m, enforce, solver)
            walls.append(parametric_serial(st))
        row["serial_warm_median_ms"] = round(statistics.median(walls), 1)
        row["serial_walls_ms"] = [round(x, 1) for x in walls]
        row.update(surface_quality(st))
        if enforce and solver == "symmetric":  # the /fit/surface route: calendar residuals + repair count
            st = new_state(chain, ladder, today, m, enforce, solver)
            t0 = time.perf_counter()
            resp = service.fit_surface(st, TICKER, "mid", True)
            row["fit_surface_serial_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
            row["calendar_residuals_max"] = max(resp.calendarResiduals) if resp.calendarResiduals else None
            row["max_iv_err_bp_per_expiry"] = [round(x, 1) for x in resp.maxIvErrorBp]
        rows.append(row)
        print("SERIAL", row, flush=True)
    out["parametric_serial"] = rows

    # ---- the whole Calibrate button for one ticker, serial: parametric (LQD-24, calendar on) + LV
    st = new_state(chain, ladder, today, "lqd", True)
    t0 = time.perf_counter()
    workflow.calibrate_ticker(st, TICKER, "mid")
    out["calibrate_ticker_serial_lqd24_cal_on_plus_lv_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
    lv0 = affine_fit.affine_payload(st, TICKER, AffineFitRequest(fitMode="mid"))
    out["calibrate_ticker_lv_rms_bp"] = {"in_operator": round(lv0.rmsIvErrorBp, 2), "converged": round(lv0.rmsConvergedBp, 2),
                                         "n_evals": lv0.nEvals}
    print("CALIBRATE_TICKER", out["calibrate_ticker_serial_lqd24_cal_on_plus_lv_ms"], flush=True)

    # ---- LV surface of the 9-rung ladder (the parametric stage precedes it in the app)
    req = AffineFitRequest(fitMode="mid")

    def lv_state(enforce: bool) -> AppState:
        s = new_state(chain, ladder, today, "lqd", enforce)
        parametric_serial(s)
        return s

    def lv_diag(s: AppState, resp) -> dict:
        d = affine_fit.last_affine_diagnostics(s, TICKER)
        keys = ("vertex_count", "pde_x_count", "pde_t_count", "quote_count", "nfev", "seed_source",
                "wall_ms_pde_sensitivity", "wall_ms_pde_value", "wall_ms_residual_assembly",
                "wall_ms_optimizer_outer", "wall_ms_total")
        return {"rms_in_operator_bp": round(resp.rmsIvErrorBp, 2), "rms_converged_bp": round(resp.rmsConvergedBp, 2),
                "max_iv_bp": round(resp.maxIvErrorBp, 2), "n_evals": resp.nEvals, "arb_free": resp.arbitrageFree,
                "calendar_violations": resp.calendarViolations, "message": resp.message,
                "diag": {k: (round(getattr(d, k), 1) if isinstance(getattr(d, k), float) else getattr(d, k))
                         for k in keys if hasattr(d, k)}}

    s_lv = lv_state(True)
    lv = {}
    walls = []
    for i in range(3):
        s_lv.set_affine_ptr(TICKER, None)
        affine_fit._cache(s_lv).clear()
        t0 = time.perf_counter()
        resp = affine_fit.calibrate_affine_surface(s_lv, TICKER, req)
        walls.append((time.perf_counter() - t0) * 1e3)
    lv["cold_start_walls_ms_jit_warm"] = [round(x, 1) for x in walls]  # the process already ran LV above
    lv["cold_start_median_ms"] = round(statistics.median(walls), 1)
    lv.update(lv_diag(s_lv, resp))
    t0 = time.perf_counter()
    resp2 = affine_fit.calibrate_affine_surface(s_lv, TICKER, req)
    lv["warm_started_recal_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
    lv["warm_started"] = lv_diag(s_lv, resp2)
    out["lv_9_rungs"] = lv
    print("LV", lv, flush=True)
    s_off = lv_state(False)
    t0 = time.perf_counter()
    resp_off = affine_fit.calibrate_affine_surface(s_off, TICKER, req)
    out["lv_9_rungs_enforceCalendar_off"] = {"ms": round((time.perf_counter() - t0) * 1e3, 1), **lv_diag(s_off, resp_off),
                                            "identical_to_on": bool(resp_off.rmsIvErrorBp == resp.rmsIvErrorBp
                                                                    and resp_off.nEvals == resp.nEvals)}
    print("LV(cal off)", out["lv_9_rungs_enforceCalendar_off"], flush=True)

    # ---- POOLED: the app's default worker count (cpu-1 capped 8)
    os.environ["VOLFIT_CALIB_WORKERS"] = "8"
    out["pool_workers"] = fit_pool.configured_workers()
    t0 = time.perf_counter()
    fit_pool.prewarm()
    with fit_pool.pooled():
        futs = [fit_pool.submit(SliceFitTask()) for _ in range(8)]
        for f in futs:
            f.result()
    out["pool_spinup_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
    print("POOL up", out["pool_spinup_ms"], flush=True)
    pooled_rows = []
    for model in ("lqd24", "svi"):
        m = "lqd" if model == "lqd24" else model
        row = {"model": model, "enforceCalendar": True, "surfaceSolver": "symmetric"}
        walls = []
        for _ in range(3):  # Calibrate-job shape: one ticker = items sequential, each fit on a worker
            st = new_state(chain, ladder, today, m, True)
            with fit_pool.pooled():
                walls.append(parametric_serial(st))
        row["pooled_calibrate_job_shape_median_ms"] = round(statistics.median(walls), 1)
        row["pooled_calibrate_job_walls_ms"] = [round(x, 1) for x in walls]
        walls = []
        for _ in range(3):  # POST /fit/surface shape: phase A fanned out over the pool
            st = new_state(chain, ladder, today, m, True)
            t0 = time.perf_counter()
            resp = service.fit_surface(st, TICKER, "mid", True)
            walls.append((time.perf_counter() - t0) * 1e3)
        row["pooled_fit_surface_fanout_median_ms"] = round(statistics.median(walls), 1)
        row["pooled_fit_surface_walls_ms"] = [round(x, 1) for x in walls]
        row.update(surface_quality(st))
        walls = []
        for _ in range(3):  # calendar OFF, Calibrate-job shape (independent items through the pool)
            st = new_state(chain, ladder, today, m, False)
            with fit_pool.pooled():
                walls.append(parametric_serial(st))
        row["pooled_calibrate_job_cal_off_median_ms"] = round(statistics.median(walls), 1)
        pooled_rows.append(row)
        print("POOLED", row, flush=True)
    out["parametric_pooled"] = pooled_rows
    # LV through the pool (one task shipped to a worker: pickling + the worker's own numba cache load)
    st = new_state(chain, ladder, today, "lqd", True)
    with fit_pool.pooled():
        parametric_serial(st)
        walls = []
        for _ in range(3):
            st.set_affine_ptr(TICKER, None)
            affine_fit._cache(st).clear()
            t0 = time.perf_counter()
            workflow_stages._affine_thunk(st, TICKER, "mid")()
            walls.append((time.perf_counter() - t0) * 1e3)
    out["lv_9_rungs_pooled_cold_start_walls_ms"] = [round(x, 1) for x in walls]
    print("LV pooled", walls, flush=True)
    fit_pool.shutdown()

    with open(os.path.join(HERE, "q3_chain.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
