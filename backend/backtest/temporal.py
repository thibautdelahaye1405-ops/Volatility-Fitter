"""Temporal prior-persistence mode scoring (Docs/prior_persistence_roadmap.md, Phase 8).

The single-snapshot harness (``run_compute`` / ``dispatch``) scores fit precision on
ONE day; prior *persistence* is a temporal behaviour — yesterday's prior carrying
the under-observed wings into today's thinned market. This module measures exactly
that, the empirical follow-on flagged in ``backtest/README.md``.

For every consecutive captured day pair (T-1, T) and asset:

  1. fit day T-1's FULL chain and freeze it as the active prior (the production
     ``priors.capture_snapshot``; transported to T's forward at fit time);
  2. on day T, THIN each expiry to its ATM region (drop the wings);
  3. refit the thinned chain under each ``priorPersistenceMode`` (off / strike_gap /
     quote_operator / smile_factor / hybrid), the prior filling the dropped wings;
  4. score the RECONSTRUCTED-WING error = model IV at the dropped wing strikes vs
     the TRUE day-T quotes there (the wings the fit never saw).

A good persistence mode reconstructs the wing it never observed; ``off`` (no prior)
is the baseline it must beat. Sweeping ``priorOperatorBandwidth`` and the var-swap
coverage probe (``operators._VARSWAP_PROBE_STD``) tunes the two defaults Phase 8
left flagged for this axis.

Run::

    python -m backtest.temporal --regime spike_aug2024
    python -m backtest.temporal --regime spike_aug2024 --asset SPX \
        --modes off,quote_operator,hybrid --bandwidths 0.04,0.06,0.10 --probes 1.0,1.4,2.0
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

import numpy as np

from volfit.api import priors, service
from volfit.calib import operators
from volfit.calib.weights import resolve_weights
from volfit.models.lqd.calibrate import calibrate_slice

from backtest.dispatch import _LQD
from backtest.replay import Fixture, list_fixtures, load_fixture, state_for_day

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

#: Persistence modes scored by default (the calibration-affecting ones; ``overlay``
#: / ``graph_only`` add no penalty so they fit identically to ``off`` here).
DEFAULT_MODES = ("off", "strike_gap", "quote_operator", "smile_factor", "hybrid")


@dataclass(frozen=True)
class NodeScore:
    """One (asset, expiry) day-T node: metadata + per-config reconstructed-wing RMS."""

    asset: str
    as_of: str  # day T
    prior_as_of: str  # day T-1
    expiry: str
    regime: str
    t: float
    atm_vol: float
    n_full: int
    n_atm: int
    n_wing: int
    off_rmse_bp: float  # the no-prior baseline (mode == off; config-invariant)
    #: (mode, bandwidth, probe) -> reconstructed-wing RMS (bp); None on a fit break.
    scores: dict


@contextmanager
def _varswap_probe(std: float):
    """Temporarily override the var-swap coverage probe width (operators reads the
    module global at call time, so this reaches every prior build in the block)."""
    saved = operators._VARSWAP_PROBE_STD
    operators._VARSWAP_PROBE_STD = std
    try:
        yield
    finally:
        operators._VARSWAP_PROBE_STD = saved


def _atm_mask(k: np.ndarray, atm_vol: float, tau: float, c_atm: float) -> np.ndarray:
    """The ATM region: strikes within ``c_atm`` ATM-standard-deviations of forward.

    ``c_atm`` σ√τ in log-moneyness is the natural width — it scales with maturity
    exactly like the delta strikes the operators place, so a short and a long expiry
    are thinned to comparable delta bands rather than a fixed k-window."""
    half = max(c_atm * atm_vol * np.sqrt(max(tau, 1e-9)), 1e-6)
    return np.abs(k) <= half


def _wing_rmse_bp(slice_, k_wing: np.ndarray, w_truth: np.ndarray, tau: float) -> float | None:
    """RMS vol error (bp) of the refit model at the held-out wing strikes vs truth.

    Non-finite model vols (a catastrophic LQD extrapolation off the thinned ATM set)
    are dropped; ``None`` when fewer than two finite wing points survive — the score
    would not be meaningful (caller treats it as a fit break)."""
    model_iv = np.sqrt(np.maximum(slice_.implied_w(k_wing), 1e-12) / tau)
    truth_iv = np.sqrt(np.maximum(w_truth, 1e-12) / tau)
    ok = np.isfinite(model_iv) & np.isfinite(truth_iv)
    if int(ok.sum()) < 2:
        return None
    return float(np.sqrt(np.mean((model_iv[ok] - truth_iv[ok]) ** 2)) * 1e4)


def _fit_thinned(state, asset, iso, prepared, k_in, w_in, weights_in):
    """Calibrate LQD-6 on the thinned ATM quotes under the state's current mode, the
    active prior filling the wings (production ``prior_targets`` -> ``calibrate_slice``)."""
    pt = service.prior_targets(state, asset, iso, k_in, weights_in, prepared)
    r = calibrate_slice(
        k_in, w_in, t=prepared.tau, n_order=6, weights=weights_in,
        operator_prior=pt.operator_prior, prior_anchor=pt.prior_anchor,
        prior_var_swap=pt.prior_var_swap, **_LQD,
    )
    return r.slice


def score_node(
    state, asset: str, expiry: date, prior_as_of: str, regime: str,
    modes, bandwidths, probes, c_atm: float, c_wing: float, min_atm: int, min_wing: int,
) -> NodeScore | None:
    """Thin one day-T node to its ATM region and score every (mode, bandwidth, probe)
    by reconstructed-wing error. ``None`` when the node lacks a matching prior node,
    enough ATM support, or enough wing strikes to score.

    The scored wings are the MODERATE band ``c_atm·σ√τ < |k| <= c_wing·σ√τ`` — the
    region the RR/BF/var-swap operators actually inform. The deep tail beyond
    ``c_wing`` σ is excluded: there no operator reaches and LQD extrapolation off a
    narrow ATM set is numerically fragile (it would only add de-Am/extrapolation
    noise to the comparison)."""
    iso = expiry.isoformat()
    # No transported prior node for this expiry ⇒ nothing to persist; skip.
    from volfit.api import prior_transport

    if prior_transport.prior_node(state.active_prior(asset), iso) is None:
        return None
    prepared = service.prepared_quotes(state, asset, expiry)  # full day-T truth
    k, w, tau = prepared.k, prepared.w_mid, prepared.tau
    if k.size == 0 or tau <= 0.0:
        return None
    atm_vol = float(np.sqrt(max(np.interp(0.0, k, w), 1e-12) / tau))
    atm = _atm_mask(k, atm_vol, tau, c_atm)
    wing = (~atm) & _atm_mask(k, atm_vol, tau, c_wing)  # moderate wings only
    if int(atm.sum()) < min_atm or int(wing.sum()) < min_wing:
        return None

    # "equal" weighting returns None (the uniform sentinel) — keep it None, don't slice.
    weights = resolve_weights("equal", k, w)
    wts_in = None if weights is None else weights[atm]
    k_in, w_in = k[atm], w[atm]
    k_wing, w_wing = k[wing], w[wing]

    def fit_rmse() -> float | None:
        try:
            sl = _fit_thinned(state, asset, iso, prepared, k_in, w_in, wts_in)
            return round(_wing_rmse_bp(sl, k_wing, w_wing, tau), 2)
        except Exception:  # noqa: BLE001 — a fit break is a missing score, not a crash
            return None

    # ``off`` is config-invariant (no prior penalty) — fit it once as the baseline.
    state.set_options(state.options().model_copy(update={"priorPersistenceMode": "off"}))
    off_rmse = fit_rmse()
    if off_rmse is None:
        return None

    scores: dict = {}
    for mode in modes:
        if mode == "off":
            continue
        state.set_options(state.options().model_copy(update={"priorPersistenceMode": mode}))
        for bw in bandwidths:
            state.set_options(state.options().model_copy(update={"priorOperatorBandwidth": bw}))
            for probe in probes:
                with _varswap_probe(probe):
                    scores[(mode, bw, probe)] = fit_rmse()

    return NodeScore(
        asset=asset, as_of=state.reference_date.isoformat(), prior_as_of=prior_as_of,
        expiry=iso, regime=regime, t=round(float(prepared.t), 5), atm_vol=round(atm_vol, 5),
        n_full=int(k.size), n_atm=int(atm.sum()), n_wing=int(wing.sum()),
        off_rmse_bp=off_rmse, scores=scores,
    )


def _day_pairs(paths: list[str]) -> dict:
    """Group fixture paths by asset -> sorted [(prior_path, today_path), ...] for
    every consecutive captured-day pair (the temporal unit)."""
    by_asset: dict[str, list[Fixture]] = defaultdict(list)
    for p in paths:
        f = load_fixture(p)
        by_asset[f.asset].append((f.as_of, p))  # type: ignore[arg-type]
    pairs: dict[str, list] = {}
    for asset, items in by_asset.items():
        items.sort()
        pairs[asset] = [(items[i - 1][1], items[i][1]) for i in range(1, len(items))]
    return pairs


def run(
    regime: str, asset: str | None, modes, bandwidths, probes,
    c_atm: float, c_wing: float, min_atm: int, min_wing: int, max_pairs: int | None,
) -> list[NodeScore]:
    """Score every consecutive day pair in a regime; one ``NodeScore`` per day-T node."""
    paths = list_fixtures(regime=regime, asset=asset)
    if not paths:
        raise SystemExit(f"no fixtures for regime={regime} asset={asset}")
    pairs = _day_pairs(paths)
    results: list[NodeScore] = []
    for tk in sorted(pairs):
        seq = pairs[tk][:max_pairs] if max_pairs else pairs[tk]
        for prior_path, today_path in seq:
            prior_fx, today_fx = load_fixture(prior_path), load_fixture(today_path)
            # Freeze day T-1's full surface as the active prior (production capture).
            state_tm1 = state_for_day([prior_fx])
            snap = priors.capture_snapshot(state_tm1, tk, "mid", lv=False)  # parametric only
            if snap is None:
                continue
            state_t = state_for_day([today_fx])
            state_t.set_active_prior(tk, snap, "saved")
            for expiry in today_fx.expiries:
                try:
                    ns = score_node(state_t, tk, expiry, prior_fx.as_of.isoformat(),
                                    regime, modes, bandwidths, probes, c_atm, c_wing,
                                    min_atm, min_wing)
                except Exception:  # noqa: BLE001 — a node break is a skipped score
                    ns = None
                if ns is not None:
                    results.append(ns)
            print(f"  {tk} {today_fx.as_of}: "
                  f"{sum(1 for r in results if r.asset == tk and r.as_of == today_fx.as_of.isoformat())} "
                  f"nodes scored", flush=True)
    return results


def _flatten(results: list[NodeScore]) -> list[dict]:
    """Tidy one row per (node, mode, bandwidth, probe), plus the off baseline + the
    per-node improvement over off (bp; positive = the prior beat no-prior)."""
    rows: list[dict] = []
    for r in results:
        base = dict(asset=r.asset, as_of=r.as_of, prior_as_of=r.prior_as_of,
                    expiry=r.expiry, regime=r.regime, t=r.t, atm_vol=r.atm_vol,
                    n_full=r.n_full, n_atm=r.n_atm, n_wing=r.n_wing)
        rows.append(dict(base, mode="off", bandwidth=None, probe=None,
                         wing_rmse_bp=r.off_rmse_bp, improvement_bp=0.0))
        for (mode, bw, probe), rmse in r.scores.items():
            rows.append(dict(base, mode=mode, bandwidth=bw, probe=probe,
                             wing_rmse_bp=rmse,
                             improvement_bp=None if rmse is None else round(r.off_rmse_bp - rmse, 2)))
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    """Aggregate by (mode, bandwidth, probe): median wing RMS + median improvement
    over off + win-rate (fraction of nodes the config beats its own off baseline)."""
    by_cfg: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if row["mode"] == "off" or row["wing_rmse_bp"] is None:
            continue
        by_cfg[(row["mode"], row["bandwidth"], row["probe"])].append(row)
    out: list[dict] = []
    for (mode, bw, probe), group in by_cfg.items():
        rmse = np.array([g["wing_rmse_bp"] for g in group], float)
        imp = np.array([g["improvement_bp"] for g in group], float)
        out.append(dict(
            mode=mode, bandwidth=bw, probe=probe, n=len(group),
            median_wing_rmse_bp=round(float(np.median(rmse)), 2),
            median_improvement_bp=round(float(np.median(imp)), 2),
            win_rate=round(float(np.mean(imp > 0.0)), 3),
        ))
    out.sort(key=lambda d: d["median_wing_rmse_bp"])
    return out


def _write(rows: list[dict], summary: list[dict], name: str) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    base = os.path.join(RESULTS_DIR, name)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump({"rows": rows, "summary": summary}, fh, default=str, indent=2)
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Temporal prior-persistence mode scoring.")
    ap.add_argument("--regime", default="spike_aug2024")
    ap.add_argument("--asset", default=None, help="restrict to one asset")
    ap.add_argument("--modes", default=",".join(DEFAULT_MODES))
    ap.add_argument("--bandwidths", default="0.06", help="comma-separated priorOperatorBandwidth sweep")
    ap.add_argument("--probes", default="1.4", help="comma-separated var-swap probe-std sweep")
    ap.add_argument("--c-atm", type=float, default=0.5,
                    help="ATM half-width in ATM-std (σ√τ); strikes within it are fed to the fit")
    ap.add_argument("--c-wing", type=float, default=2.0,
                    help="outer scored-wing edge in ATM-std; c_atm·σ√τ < |k| <= c_wing·σ√τ is held out")
    ap.add_argument("--min-atm", type=int, default=5, help="min ATM strikes to fit a thinned node")
    ap.add_argument("--min-wing", type=int, default=3, help="min wing strikes to score reconstruction")
    ap.add_argument("--max-pairs", type=int, default=None, help="cap day pairs per asset (smoke runs)")
    args = ap.parse_args()

    modes = tuple(m.strip() for m in args.modes.split(","))
    bandwidths = tuple(float(b) for b in args.bandwidths.split(","))
    probes = tuple(float(p) for p in args.probes.split(","))
    print(f"regime={args.regime} asset={args.asset or '*'} modes={modes} "
          f"bandwidths={bandwidths} probes={probes} c_atm={args.c_atm}", flush=True)

    results = run(args.regime, args.asset, modes, bandwidths, probes,
                  args.c_atm, args.c_wing, args.min_atm, args.min_wing, args.max_pairs)
    rows = _flatten(results)
    summary = summarize(rows)
    base = _write(rows, summary, f"{args.regime}_temporal_prior")
    print(f"\nwrote {base}.json  ({len(results)} nodes, {len(rows)} rows)\n")
    print(f"{'mode':<15}{'bw':>6}{'probe':>7}{'n':>5}{'medRMS':>9}{'medImp':>9}{'win':>7}")
    for s in summary:
        print(f"{s['mode']:<15}{s['bandwidth']:>6}{s['probe']:>7}{s['n']:>5}"
              f"{s['median_wing_rmse_bp']:>9}{s['median_improvement_bp']:>9}{s['win_rate']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
