"""Compute-phase driver — sweep models/hyperparameters over the captured fixtures.

Replays every captured (asset, date) offline and, per node, fits the parametric
model sweep (``dispatch.fit_node``) and optionally the piecewise-affine Local-Vol
surface (the production ``calibrate_affine_surface`` + its diagnostics). Writes one
tidy metrics table (Parquet + CSV) for the analysis / break-triage / report phases.

Run:

    python -m backtest.run_compute --regime spike_aug2024            # parametric
    python -m backtest.run_compute --regime spike_aug2024 --lv       # + LV surface
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict

from volfit.api.affine_fit import calibrate_affine_surface, last_affine_diagnostics
from volfit.api.schemas_affine import AffineFitRequest

from backtest.dispatch import DEFAULT_SWEEP, fit_node
from backtest.replay import Fixture, list_fixtures, load_fixture, state_for_day

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def _parametric_rows(state, fixtures: list[Fixture], weight_scheme: str,
                     fit_mode: str, specs) -> list[dict]:
    """Fit the model sweep for every node in one as-of day's fixtures (the de-Am is
    memoized on ``state``, so reusing it across weight/fit-mode combos is cheap)."""
    rows: list[dict] = []
    for f in fixtures:
        for expiry in f.expiries:
            try:
                rows.extend(
                    fit_node(state, f.asset, expiry, f.regime, f.sector,
                             f.exercise_style, specs=specs, weight_scheme=weight_scheme,
                             fit_mode=fit_mode)
                )
            except Exception as exc:  # noqa: BLE001 - a node break is a recorded result
                rows.append(dict(
                    asset=f.asset, as_of=f.as_of.isoformat(), regime=f.regime,
                    expiry=expiry.isoformat(), model="*node*", ok=False,
                    error=type(exc).__name__ + ": " + str(exc)[:140],
                ))
    return rows


def _lv_rows(state, fixtures: list[Fixture]) -> list[dict]:
    """Fit the production Local-Vol surface per asset; one row per (asset, expiry)."""
    rows: list[dict] = []
    for f in fixtures:
        try:
            resp = calibrate_affine_surface(state, f.asset, AffineFitRequest())
            d = last_affine_diagnostics(state, f.asset)
        except Exception as exc:  # noqa: BLE001
            rows.append(dict(
                asset=f.asset, as_of=f.as_of.isoformat(), regime=f.regime,
                model="LV", ok=False, error=type(exc).__name__ + ": " + str(exc)[:140],
            ))
            continue
        for sm in resp.smiles:
            rows.append(dict(
                asset=f.asset, as_of=f.as_of.isoformat(), regime=f.regime,
                sector=f.sector, exercise_style=f.exercise_style, model="LV",
                expiry=str(sm.expiry), in_rmse_bp=round(sm.rmsError * 1e4, 2),
                max_err_bp=round(sm.maxIvErrorBp, 2), n_quotes=len(sm.quotes),
                surface_rmse_bp=round(resp.surfaceRmsError * 1e4, 2),
                vertex_count=d.vertex_count, nfev=d.nfev, max_nfev=d.max_nfev,
                njev=d.njev, status=d.status, active_bound_count=d.active_bound_count,
                hit_max_nfev=bool(d.nfev >= d.max_nfev),
                wall_ms_total=round(d.wall_ms_total, 1),
                wall_ms_pde_value=round(d.wall_ms_pde_value, 1),
                wall_ms_pde_sensitivity=round(d.wall_ms_pde_sensitivity, 1),
                wall_ms_assembly=round(d.wall_ms_residual_assembly, 1),
                wall_ms_optimizer=round(d.wall_ms_optimizer_outer, 1),
                ok=True,
            ))
    return rows


def _write(rows: list[dict], name: str) -> str:
    """Persist the metrics table as typed JSON (dependency-free); Parquet too if
    pyarrow is available (preferred for the downstream NN dataset)."""
    import json

    os.makedirs(RESULTS_DIR, exist_ok=True)
    base = os.path.join(RESULTS_DIR, name)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(rows, fh, default=str)
    try:
        import pandas as pd

        pd.DataFrame(rows).to_parquet(base + ".parquet", index=False)
    except Exception:  # noqa: BLE001 - parquet is a best-effort bonus
        pass
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Sweep models over captured fixtures.")
    ap.add_argument("--regime", default="spike_aug2024")
    ap.add_argument("--asset", default=None, help="restrict to one asset")
    ap.add_argument("--lv", action="store_true", help="also fit the Local-Vol surface")
    ap.add_argument("--weights", default="equal,tv_density",
                    help="comma-separated weighting schemes (equal|tv_density)")
    ap.add_argument("--fit-modes", default="mid,haircut",
                    help="comma-separated fit targets (mid|haircut)")
    ap.add_argument("--models", default=None,
                    help="comma-separated model labels to keep (default: the full "
                         "sweep). e.g. SVI-JW,LQD-6,LQD-8,LQD-10,LQD-12,SIV-0 drops "
                         "the slow, non-viable SIV-1/2/3 for the scaled batches.")
    args = ap.parse_args()
    weights = [w.strip() for w in args.weights.split(",")]
    fit_modes = [m.strip() for m in args.fit_modes.split(",")]
    specs = DEFAULT_SWEEP
    if args.models:
        keep = {m.strip() for m in args.models.split(",")}
        specs = tuple(s for s in DEFAULT_SWEEP if s.label in keep)
        if not specs:
            raise SystemExit(f"--models matched no sweep labels: {keep}")

    paths = list_fixtures(regime=args.regime, asset=args.asset)
    if not paths:
        raise SystemExit(f"no fixtures for regime={args.regime} asset={args.asset}")
    by_date: dict = defaultdict(list)
    for p in paths:
        f = load_fixture(p)
        by_date[f.as_of].append(f)
    print(f"{len(paths)} fixtures over {len(by_date)} days; "
          f"sweep={[s.label for s in specs]}; "
          f"weights={weights} fit_modes={fit_modes}", flush=True)

    # One row list per (weight, fit_mode) combo; LV is fit-target-independent here.
    par: dict[tuple[str, str], list[dict]] = {(w, m): [] for w in weights for m in fit_modes}
    lv_rows: list[dict] = []
    for as_of in sorted(by_date):
        fixtures = by_date[as_of]
        state = state_for_day(fixtures)  # built once; de-Am memoized across combos
        for w in weights:
            for m in fit_modes:
                par[(w, m)].extend(_parametric_rows(state, fixtures, w, m, specs))
        if args.lv:
            lv_rows.extend(_lv_rows(state, fixtures))
        print(f"  {as_of}: {len(fixtures)} assets done"
              f"{' (+LV)' if args.lv else ''}", flush=True)

    for (w, m), rows in par.items():
        base = _write(rows, f"{args.regime}_parametric_{w}_{m}")
        print(f"wrote {base}.json  ({len(rows)} rows)")
    if args.lv:
        base = _write(lv_rows, f"{args.regime}_localvol")
        print(f"wrote {base}.json  ({len(lv_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
