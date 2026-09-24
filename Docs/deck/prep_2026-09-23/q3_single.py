"""Q3 (speed): SINGLE-NODE compute attribution on the Massive live SPY chain
(q3_chains.pkl, fetched by q3_fetch.py). Node = SPY 2026-10-16 (the monthly,
23 days). Everything runs IN-PROCESS through the app's own service/AppState
path (the replay pattern of q2_0dte_demo.py); stage timers are wrapped around
the real pipeline functions (forwards._fit / _refine_american, quotes.
_early_exercise_premiums / deamericanize_batch / implied_total_variance /
convex_wing_repair, calibrate_slice, build_display_fit, calibrate_affine_surface).

Run from backend\ :  ..\.venv\Scripts\python <this file>
Serial: VOLFIT_CALIB_WORKERS=1 (inline fits). Cold = the first call in this
fresh process (Numba cache loads / JIT included); warm = median of 3 repeats
on fresh caches (the fit itself re-runs every time, only the interpreter, the
Numba kernels and the LQD quadrature tables are warm).
"""
from __future__ import annotations

import functools
import json
import os
import statistics
import sys
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["VOLFIT_CALIB_WORKERS"] = "1"

import numpy as np  # noqa: E402

from volfit.api import affine_fit, service  # noqa: E402
from volfit.api import quotes as quotes_mod  # noqa: E402
from volfit.api.schemas import FitSettings  # noqa: E402
from volfit.api.schemas_affine import AffineFitRequest  # noqa: E402
from volfit.api.state import AppState  # noqa: E402
from volfit.calib.fit_task import run_slice_fit  # noqa: E402
from volfit.data import forwards as fwd_mod  # noqa: E402
from volfit.models.display import build_display_fit  # noqa: E402
from volfit.replay_report import _StoredChains  # noqa: E402

TICKER = "SPY"
NODE = date(2026, 10, 16)
NEXT = date(2026, 11, 20)


# ----------------------------------------------------------------- timers
class Tally:
    """Accumulates wall time per wrapped function (nested wrappers overlap)."""

    def __init__(self) -> None:
        self.t: dict[str, list[float]] = {}

    def wrap(self, module, name: str, label: str | None = None):
        fn = getattr(module, name)
        label = label or name
        if getattr(fn, "_q3_wrapped", False):
            return

        @functools.wraps(fn)
        def timed(*a, **kw):
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                self.t.setdefault(label, []).append(time.perf_counter() - t0)

        timed._q3_wrapped = True
        setattr(module, name, timed)

    def reset(self) -> None:
        self.t = {}

    def report(self) -> dict:
        return {k: {"calls": len(v), "ms": round(sum(v) * 1e3, 2)} for k, v in self.t.items()}


TALLY = Tally()
TALLY.wrap(fwd_mod, "_fit", "forward.parity_regression_lsq")
TALLY.wrap(fwd_mod, "_refine_american", "forward.deam_debias_fixed_point")
TALLY.wrap(fwd_mod, "deamericanize_batch", "forward.crr_batch_inside_debias")
TALLY.wrap(quotes_mod, "_pre_deam_screen", "prep.pre_deam_screen")
TALLY.wrap(quotes_mod, "_early_exercise_premiums", "prep.deam_eep_total")
TALLY.wrap(quotes_mod, "deamericanize_batch", "prep.crr192_batch_inversion")
TALLY.wrap(quotes_mod, "implied_total_variance", "prep.black_inversions")
TALLY.wrap(quotes_mod, "convex_wing_repair", "prep.convex_wing_repair")


def timed(fn, reps: int = 3) -> tuple[float, list[float]]:
    walls = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        walls.append((time.perf_counter() - t0) * 1e3)
    return statistics.median(walls), walls


def load():
    import pickle

    with open(os.path.join(HERE, "q3_chains.pkl"), "rb") as fh:
        data = pickle.load(fh)
    return data["chains"]["massive_live"], data["ladder"], data["today"]


def new_state(chain, ladder, today, **fit_settings) -> AppState:
    st = AppState(today, provider=_StoredChains({TICKER: chain}))
    st.set_expiries(TICKER, ladder)
    if fit_settings:
        st.set_fit_settings(FitSettings(**fit_settings))
    return st


def rms_bp(slice_, k, w, tau) -> tuple[float, float]:
    model = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / tau)
    mid = np.sqrt(np.maximum(w, 1e-12) / tau)
    err = (model - mid) * 1e4
    return float(np.sqrt(np.mean(err**2))), float(np.max(np.abs(err)))


def main() -> None:
    out: dict = {"node": NODE.isoformat(), "ticker": TICKER}
    chain, ladder, today = load()
    iso = NODE.isoformat()
    out["chain"] = {"spot": chain.spot, "timestamp": str(chain.timestamp), "quotes": len(chain.quotes),
                    "ladder": [e.isoformat() for e in ladder], "reference_date": today.isoformat()}
    out["versions"] = {"python": sys.version.split()[0]}
    import numba, scipy
    out["versions"].update(numpy=np.__version__, scipy=scipy.__version__, numba=numba.__version__)

    # ---- stage 2a: forwards (parity regression + de-Am de-bias), whole ticker then one expiry
    st = new_state(chain, ladder, today)
    TALLY.reset()
    t0 = time.perf_counter()
    fwds = st.forwards(TICKER)  # cold: first CRR call in the process (Numba cache load)
    cold_fwd = (time.perf_counter() - t0) * 1e3
    out["forwards_all_expiries_cold"] = {"ms": round(cold_fwd, 1), "expiries": len(fwds), "inner": TALLY.report()}

    def fwd_all():
        s = new_state(chain, ladder, today)
        s.forwards(TICKER)

    TALLY.reset()
    med, walls = timed(fwd_all)
    out["forwards_all_expiries_warm"] = {"median_ms": round(med, 1), "walls_ms": [round(x, 1) for x in walls],
                                         "inner_3runs": TALLY.report()}
    TALLY.reset()
    med, walls = timed(lambda: fwd_mod.implied_forward(chain, NODE, today))
    out["forward_one_expiry_warm"] = {"median_ms": round(med, 2), "walls_ms": [round(x, 2) for x in walls],
                                      "inner_3runs": TALLY.report()}
    TALLY.reset()
    med, walls = timed(lambda: fwd_mod.implied_forward(chain, NODE, None))
    out["forward_one_expiry_raw_regression_only_warm"] = {"median_ms": round(med, 2), "inner_3runs": TALLY.report()}
    f = fwds[NODE]
    out["forward_node"] = {"forward": f.forward, "discount": f.discount, "n_strikes": f.n_strikes,
                           "residual_rms": f.residual_rms}

    # ---- stage 2b: quote prep (screen + de-Am + inversion + convex repair), cold then warm
    TALLY.reset()
    t0 = time.perf_counter()
    prepared = service.prepared_quotes(st, TICKER, NODE)
    cold_prep = (time.perf_counter() - t0) * 1e3
    out["prepared_quotes_cold"] = {"ms": round(cold_prep, 1), "inner": TALLY.report()}

    def prep_fresh():
        st._prepared.clear()
        service.prepared_quotes(st, TICKER, NODE)

    TALLY.reset()
    med, walls = timed(prep_fresh)
    out["prepared_quotes_warm"] = {"median_ms": round(med, 2), "walls_ms": [round(x, 2) for x in walls],
                                   "inner_3runs": TALLY.report()}
    raw_rows = sum(1 for q in chain.quotes if q.expiry == NODE)
    out["prepared_node"] = {"raw_quotes_both_sides": raw_rows, "n_deam_input": prepared.n_deam_input,
                            "n_deamericanized": prepared.n_deamericanized, "n_fit_quotes": int(prepared.k.size),
                            "screened": len(prepared.screened), "t_days": prepared.t * 365.0,
                            "k_min": float(prepared.k.min()), "k_max": float(prepared.k.max()),
                            "vega_floored": prepared.vega_floored}

    # ---- stage 3: LQD-24 slice fit (the exact pool/inline code path: run_slice_fit)
    def lqd_case(n_order: int, cold: bool):
        s = new_state(chain, ladder, today, nOrder=n_order)  # model="lqd" (default)
        p = service.prepared_quotes(s, TICKER, NODE)
        t0 = time.perf_counter()
        task = service.single_node_task(s, TICKER, iso, p, "mid", None, None)
        build_ms = (time.perf_counter() - t0) * 1e3
        rec = {"task_build_ms": round(build_ms, 2), "n_order_effective": task.calibrate["n_order"],
               "n_quotes": int(task.calibrate["k"].size), "coords": task.calibrate["coords"]}
        if cold:
            t0 = time.perf_counter()
            res = run_slice_fit(task).result
            rec["cold_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
        holder = {}

        def run():
            holder["res"] = run_slice_fit(task).result

        med, walls = timed(run)
        res = holder["res"]
        r, m = rms_bp(res.slice, task.calibrate["k"], task.calibrate["w_quotes"], p.tau)
        rec.update(warm_median_ms=round(med, 1), walls_ms=[round(x, 1) for x in walls],
                   rms_bp=round(r, 2), max_err_bp=round(m, 2), n_eval=res.n_evaluations,
                   success=res.success, cost=res.cost)
        return rec

    out["lqd24"] = lqd_case(24, cold=True)
    out["lqd16"] = lqd_case(16, cold=False)

    # ---- stage 4: SVI-JW overlay (the app fits the LQD backbone + the SVI overlay in ONE task)
    s = new_state(chain, ladder, today, model="svi", nOrder=24)
    p = service.prepared_quotes(s, TICKER, NODE)
    task = service.single_node_task(s, TICKER, iso, p, "mid", None, None)
    t0 = time.perf_counter()
    disp = build_display_fit(**task.overlay)
    cold_svi = (time.perf_counter() - t0) * 1e3
    holder = {}

    def svi_run():
        holder["d"] = build_display_fit(**task.overlay)

    med, walls = timed(svi_run)
    disp = holder["d"]
    r, m = rms_bp(disp.slice, task.overlay["k"], task.overlay["w"], p.tau)
    out["svi_overlay"] = {"cold_ms": round(cold_svi, 1), "warm_median_ms": round(med, 1),
                          "walls_ms": [round(x, 1) for x in walls], "rms_bp": round(r, 2), "max_err_bp": round(m, 2),
                          "chart": task.overlay["settings"].sviChart, "belly_repaired": disp.belly_repaired,
                          "n_quotes": int(task.overlay["k"].size)}
    med, walls = timed(lambda: run_slice_fit(task))
    out["svi_node_task_lqd24_plus_svi"] = {"warm_median_ms": round(med, 1), "walls_ms": [round(x, 1) for x in walls]}

    # ---- the full single-node Calibrate path (service.calibrate_node = key + prep hit + fit + commit)
    def node_calibrate(model: str):
        s2 = new_state(chain, ladder, today, model=model, nOrder=24)
        service.prepared_quotes(s2, TICKER, NODE)  # prep is memoized in the app; keep it out of the fit number
        s2.forwards(TICKER)

        def run():
            s2._fits.clear()
            service.calibrate_node(s2, TICKER, iso, "mid")

        med, walls = timed(run)
        rec = service.calibrate_node(s2, TICKER, iso, "mid")
        return {"warm_median_ms": round(med, 1), "walls_ms": [round(x, 1) for x in walls],
                "displayed_rms_bp": round(service.weighted_rms_error(s2, TICKER, iso, rec, "mid") * 1e4, 2)}

    out["calibrate_node_lqd24"] = node_calibrate("lqd")
    out["calibrate_node_svi"] = node_calibrate("svi")

    # ---- stage 5: LV (affine) — a per-ticker SURFACE fit; the smallest legal surface = 2 expiries
    s3 = new_state(chain, ladder, today, nOrder=24)
    s3.set_expiries(TICKER, [NODE, NEXT])
    for e in (NODE, NEXT):
        service.calibrate_node(s3, TICKER, e.isoformat(), "mid")  # the parametric stage precedes LV in the app
    req = AffineFitRequest(fitMode="mid")
    t0 = time.perf_counter()
    resp = affine_fit.calibrate_affine_surface(s3, TICKER, req)
    cold_lv = (time.perf_counter() - t0) * 1e3
    diag = affine_fit.last_affine_diagnostics(s3, TICKER)
    lv = {"cold_ms": round(cold_lv, 1), "expiries": resp.smiles and [sm.expiry for sm in resp.smiles],
          "rms_iv_bp_in_operator": round(resp.rmsIvErrorBp, 2), "rms_converged_bp": round(resp.rmsConvergedBp, 2),
          "max_iv_bp": round(resp.maxIvErrorBp, 2), "n_evals": resp.nEvals, "arb_free": resp.arbitrageFree,
          "calendar_violations": resp.calendarViolations, "message": resp.message,
          "diag_cold": {k: getattr(diag, k) for k in ("vertex_count", "pde_x_count", "pde_t_count", "quote_count",
                                                        "seed_source", "wall_ms_pde_sensitivity",
                                                        "wall_ms_optimizer_outer") if hasattr(diag, k)}}

    def lv_cold_start():  # JIT warm, but the surface starts from the parametric seed (no previous surface)
        s3.set_affine_ptr(TICKER, None)
        affine_fit._cache(s3).clear()
        affine_fit.calibrate_affine_surface(s3, TICKER, req)

    med, walls = timed(lv_cold_start)
    diag = affine_fit.last_affine_diagnostics(s3, TICKER)
    lv["warm_jit_cold_start_median_ms"] = round(med, 1)
    lv["walls_ms"] = [round(x, 1) for x in walls]
    lv["diag_warm"] = {k: getattr(diag, k) for k in ("n_evals", "seed_source", "wall_ms_pde_sensitivity",
                                                     "wall_ms_optimizer_outer", "wall_ms_total") if hasattr(diag, k)}
    t0 = time.perf_counter()
    resp2 = affine_fit.calibrate_affine_surface(s3, TICKER, req)  # warm-STARTED from the previous surface
    lv["warm_started_recal_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
    lv["warm_started_n_evals"] = resp2.nEvals
    lv["diag_fields"] = [k for k in dir(diag) if not k.startswith("_")] if diag is not None else []
    out["lv_two_expiry_surface"] = lv

    with open(os.path.join(HERE, "q3_single.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
