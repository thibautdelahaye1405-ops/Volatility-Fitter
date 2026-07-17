"""Learned shrunk betas from stored benchmark innovations (roadmap R3 item 14).

The graph's cross-asset betas are hand-set vol-normalized constants
(EdgeConfig: index 0.7, sector-ETF 0.8, name 0.6, calendar sqrt(T ratio)).
This module ESTIMATES them from the captured history and shrinks hard toward
those same defaults — 3 regimes x 25 assets is thin, so the data is allowed
to nudge the prior, never to replace it.

Data: the stored benchmark part rows (results/benchmark/*.json). Each scored
row carries ``base_atm`` = transported_prior - calibrated at that node/day —
the NEGATIVE of the node's ATM innovation, and independent of every solver
knob (baseline and truth never see the solve), so rows from any sweep tag can
be pooled. Ticker-day innovations are the median across the ticker's scored
expiries; vol-normalization uses a per-(regime, ticker) ATM-vol scale read
fit-free from the first estimation day's fixtures (service.prepare_slice).

STRICT TIME-SPLIT: only the first ``split`` fraction of each regime's day
pairs feeds the regressions; the artifact records ``evalPairStart`` so the
adjudication sweep (benchmark_pack --pair-start) scores ONLY the later days.

Estimated cells (through-origin regressions, slope b = sum(xy)/sum(x^2)).
DELIBERATELY PREDICTIVE, not structural: the graph consumes beta to predict
the influenced node's move FROM the informer's observed innovation, so the
conditional-expectation (OLS) slope — attenuation included, since prediction
time sees the same noisy informer — is the decision-relevant object; a
noise-corrected structural beta would over-propagate. Cells:
  * index -> name, PER NAME:  z_name = b * z_index      (prior 0.7)
  * name <-> name same sector, ONE CLASS: z_i = b * z_j (prior 0.6)
  * sector-ETF -> name, ONE CLASS                        (prior 0.8; dormant
    on this universe — EEM/EFA share no sector with any name — kept for when
    a US sector ETF is captured)
  * calendar within underlying, ONE MULTIPLIER on sqrt(T_long/T_short)
    (prior 1.0; not vol-normalized — same ticker)

Shrinkage + auto-reject (the roadmap's "shrink hard / auto-reject unstable or
sign-flipping edges"): b_shrunk = (n*b + K*prior)/(n + K) with K=20 equivalent
observations; an estimate reverts to its prior exactly when n < 8, |t| < 2,
or sign(b) != sign(prior). Every cell ships raw/shrunk/n/t/reason — the
artifact is the audit trail, and the edges it produces stay per-edge editable
downstream (GraphEdgeInput).

Run::

    python -m backtest.learn_betas fit            # writes results/learned_betas.json
    python -m backtest.learn_betas show           # prints the artifact table
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone

import numpy as np

from backtest.graph_edges import BetaOverrides, EdgeConfig, asset_kind, asset_sector

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DEFAULT_OUT = os.path.join(RESULTS_DIR, "learned_betas.json")

SHRINK_K = 20  # prior weight in equivalent observations (hard shrink)
MIN_N = 8  # fewer pooled observations than this -> keep the prior
MIN_T = 2.0  # |t| below this -> unstable -> keep the prior
_ATM_BAND = 0.10  # |k| band for the sigma-scale read


# ------------------------------------------------------------------ regression
def _slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    """(slope, t_stat, n) of the through-origin regression y = b x."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(x.size)
    sxx = float(x @ x)
    if n < 2 or sxx <= 0.0:
        return 0.0, 0.0, n
    b = float(x @ y) / sxx
    resid = y - b * x
    se2 = float(resid @ resid) / max(n - 1, 1) / sxx
    t = b / np.sqrt(se2) if se2 > 0.0 else 0.0
    return b, float(t), n


def shrink_estimate(raw: float, t: float, n: int, prior: float, cap: float) -> dict:
    """One estimated cell: hard shrinkage toward the prior + auto-reject.

    The returned ``beta`` is what production consumes; ``rejected`` cells carry
    the prior EXACTLY (the roadmap's auto-reject bar), with the raw evidence
    kept for the audit trail."""
    reason = None
    if n < MIN_N:
        reason = f"n<{MIN_N}"
    elif abs(t) < MIN_T:
        reason = f"|t|<{MIN_T:g}"
    elif raw * prior < 0.0 or raw < 0.0:
        reason = "sign_flip"
    elif not (0.0 <= raw <= cap):
        reason = "outside_cap"
    beta = prior if reason else (n * raw + SHRINK_K * prior) / (n + SHRINK_K)
    return {
        "beta": round(float(beta), 4),
        "raw": round(float(raw), 4),
        "n": n,
        "t": round(float(t), 2),
        "prior": prior,
        "rejected": reason is not None,
        "reason": reason,
    }


# ------------------------------------------------------------ stored-row panel
def _load_rows() -> list[dict]:
    from backtest.benchmark_pack import load_parts

    rows = [r for r in load_parts() if r.get("design") == "full_loo"]
    if not rows:
        raise SystemExit(
            "no stored full_loo benchmark rows under results/benchmark/ — "
            "run the benchmark pack first"
        )
    return rows


def _estimation_days(rows: list[dict], split: float) -> tuple[dict, dict]:
    """Per regime: the estimation-day set (first ``split`` of scored days) and
    the pair index evaluation must start at (= number of estimation days)."""
    days: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["as_of"] not in days[r["regime"]]:
            days[r["regime"]].append(r["as_of"])
    est, eval_start = {}, {}
    for regime, ds in days.items():
        ds = sorted(ds)
        n_est = max(int(np.ceil(len(ds) * split)), 1)
        est[regime] = frozenset(ds[:n_est])
        eval_start[regime] = n_est
    return est, eval_start


def _innovation_panel(rows: list[dict], est_days: dict, ssr: int) -> dict:
    """{(regime, day, ticker): ATM innovation} — median across the ticker's
    scored expiries; estimation days only. Innovation d = -base_atm."""
    cell: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        if int(r.get("ssr", -1)) != ssr or r.get("base_atm") is None:
            continue
        if r["as_of"] not in est_days.get(r["regime"], ()):
            continue
        cell[(r["regime"], r["as_of"], r["ticker"])].append(-float(r["base_atm"]))
    return {k: float(np.median(v)) for k, v in cell.items()}


def _expiry_panel(rows: list[dict], est_days: dict, ssr: int) -> dict:
    """{(regime, day, ticker, expiry): innovation} for the calendar regression."""
    out: dict[tuple, float] = {}
    for r in rows:
        if int(r.get("ssr", -1)) != ssr or r.get("base_atm") is None:
            continue
        if r["as_of"] not in est_days.get(r["regime"], ()):
            continue
        out[(r["regime"], r["as_of"], r["ticker"], r["expiry"])] = -float(r["base_atm"])
    return out


# ------------------------------------------------------------- sigma-vol scale
def _sigma_table(est_days: dict) -> dict[tuple[str, str], float]:
    """{(regime, ticker): ATM-vol scale} read FIT-FREE from the first estimation
    day's fixtures (prepared near-ATM mid IV, median expiry). Missing tickers
    simply drop out of the normalized regressions."""
    from volfit.api import service

    from backtest.replay import list_fixtures, load_fixture, state_for_day

    out: dict[tuple[str, str], float] = {}
    for regime, days in est_days.items():
        day0 = min(days)
        fixtures = [
            load_fixture(p)
            for p in list_fixtures(regime=regime)
            if load_fixture(p).as_of.isoformat() == day0
        ]
        if not fixtures:
            continue
        state = state_for_day(fixtures)
        for tk in sorted({f.asset for f in fixtures}):
            try:
                state.ensure_chain(tk)  # prepare_slice serves nothing unfetched
                isos = [e.isoformat() for e in sorted(state.selected_expiries(tk))]
                if not isos:
                    continue
                prepared = service.prepare_slice(state, tk, isos[len(isos) // 2])
                if prepared is None:
                    continue
                k = np.asarray(prepared.k, dtype=float)
                iv = np.asarray(prepared.iv_mid, dtype=float)
                near = iv[np.abs(k) <= _ATM_BAND]
                sigma = float(np.median(near if near.size else iv))
                if np.isfinite(sigma) and sigma > 0.0:
                    out[(regime, tk)] = sigma
            except Exception:  # noqa: BLE001 — a scale miss drops the ticker
                continue
    return out


# ---------------------------------------------------------------------- pairs
def _paired(panel: dict, sigma: dict, pick_y, pick_x) -> tuple[np.ndarray, np.ndarray]:
    """Pooled (x, y) arrays of vol-normalized innovations across (regime, day)."""
    by_day: dict[tuple, dict[str, float]] = defaultdict(dict)
    for (regime, day, tk), d in panel.items():
        s = sigma.get((regime, tk))
        if s:
            by_day[(regime, day)][tk] = d / s
    xs, ys = [], []
    for z in by_day.values():
        for tk_y, tk_x in pick_pairs(z, pick_y, pick_x):
            ys.append(z[tk_y])
            xs.append(z[tk_x])
    return np.array(xs), np.array(ys)


def pick_pairs(z: dict[str, float], pick_y, pick_x):
    for tk_y in z:
        if not pick_y(tk_y):
            continue
        for tk_x in z:
            if tk_x != tk_y and pick_x(tk_y, tk_x):
                yield tk_y, tk_x


def _calendar_xy(expiry_panel: dict) -> tuple[np.ndarray, np.ndarray]:
    """Pooled (x, y) for the calendar multiplier over adjacent scored expiries,
    BOTH directions (y = d_a, x = sqrt(t_b/t_a) * d_b for each ordering) —
    the edge builder applies one multiplier symmetrically to both directed
    calendar edges, so the fit minimizes the same symmetric prediction error."""
    ladders: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for (regime, day, tk, iso), d in expiry_panel.items():
        t = (date.fromisoformat(iso) - date.fromisoformat(day)).days / 365.0
        if t > 0:
            ladders[(regime, day, tk)].append((t, d))
    xs, ys = [], []
    for pts in ladders.values():
        pts.sort()
        for (t_s, d_s), (t_l, d_l) in zip(pts[:-1], pts[1:]):
            xs.append(np.sqrt(t_l / t_s) * d_l)
            ys.append(d_s)
            xs.append(np.sqrt(t_s / t_l) * d_s)
            ys.append(d_l)
    return np.array(xs), np.array(ys)


# ------------------------------------------------------------------------- fit
def fit(split: float = 0.5, ssr: int = 0, out_path: str = DEFAULT_OUT) -> dict:
    """Estimate + shrink every learnable cell; write the versioned artifact."""
    cfg = EdgeConfig()
    rows = _load_rows()
    est_days, eval_start = _estimation_days(rows, split)
    panel = _innovation_panel(rows, est_days, ssr)
    sigma = _sigma_table(est_days)

    hub = cfg.market_indices[0]
    names = sorted({tk for (_r, _d, tk) in panel if asset_kind(tk) == "name"})
    index_by_name = {}
    for name in names:
        x, y = _paired(
            panel, sigma, lambda t, n=name: t == n, lambda _y, t: t == hub
        )
        b, t_stat, n = _slope(x, y)
        index_by_name[name] = shrink_estimate(b, t_stat, n, cfg.beta_index, cfg.beta_cap)

    x, y = _paired(
        panel, sigma,
        lambda t: asset_kind(t) == "name",
        lambda ty, tx: asset_kind(tx) == "name" and asset_sector(tx) == asset_sector(ty),
    )
    name_cell = shrink_estimate(*_slope(x, y), cfg.beta_name, cfg.beta_cap)

    x, y = _paired(
        panel, sigma,
        lambda t: asset_kind(t) == "name",
        lambda ty, tx: asset_kind(tx) == "etf" and asset_sector(tx) == asset_sector(ty),
    )
    etf_cell = shrink_estimate(*_slope(x, y), cfg.beta_etf, cfg.beta_cap)

    x, y = _calendar_xy(_expiry_panel(rows, est_days, ssr))
    cal_cell = shrink_estimate(*_slope(x, y), 1.0, cfg.beta_cap)

    artifact = {
        "version": 1,
        "kind": "learned_betas",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "estimation": {
            "split": split,
            "ssr": ssr,
            "shrinkK": SHRINK_K,
            "minN": MIN_N,
            "minT": MIN_T,
            "estimationDays": {r: sorted(d) for r, d in est_days.items()},
            "sigmaScales": {f"{r}|{tk}": round(s, 4) for (r, tk), s in sorted(sigma.items())},
        },
        "evalPairStart": eval_start,
        "indexByName": index_by_name,
        "nameBeta": name_cell,
        "etfBeta": etf_cell,
        "calendarMult": cal_cell,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2)
    return artifact


def load_overrides(path: str) -> BetaOverrides:
    """The artifact as EdgeConfig-consumable overrides (rejected cells carry
    their prior EXACTLY, so a fully-rejected artifact reproduces the default
    edges bit-for-bit)."""
    with open(path, encoding="utf-8") as fh:
        art = json.load(fh)
    return BetaOverrides(
        index_by_name={k: v["beta"] for k, v in art["indexByName"].items()},
        name_beta=art["nameBeta"]["beta"],
        etf_beta=art["etfBeta"]["beta"],
        calendar_mult=art["calendarMult"]["beta"],
    )


def _show(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        art = json.load(fh)
    est = art["estimation"]
    print(f"learned_betas v{art['version']} · {art['generatedAt']} · "
          f"split={est['split']} ssr={est['ssr']} K={est['shrinkK']}")
    print(f"eval pair start: {art['evalPairStart']}")
    hdr = f"{'cell':<22}{'beta':>8}{'raw':>8}{'n':>6}{'t':>7}  status"
    print(hdr)

    def _line(label: str, c: dict) -> None:
        status = f"REJECTED ({c['reason']})" if c["rejected"] else "learned"
        print(f"{label:<22}{c['beta']:>8}{c['raw']:>8}{c['n']:>6}{c['t']:>7}  "
              f"{status} (prior {c['prior']})")

    for name, c in sorted(art["indexByName"].items()):
        _line(f"index->{name}", c)
    _line("name<->name (class)", art["nameBeta"])
    _line("etf->name (class)", art["etfBeta"])
    _line("calendar mult", art["calendarMult"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Learned shrunk graph betas (R3 item 14).")
    ap.add_argument("command", choices=("fit", "show"))
    ap.add_argument("--split", type=float, default=0.5,
                    help="estimation fraction of each regime's day pairs (strict prefix)")
    ap.add_argument("--ssr", type=int, default=0, help="SSR regime rows to learn from")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    if args.command == "show":
        _show(args.out)
        return 0
    art = fit(split=args.split, ssr=args.ssr, out_path=args.out)
    print(f"wrote {args.out}")
    _show(args.out)
    n_rej = sum(c["rejected"] for c in art["indexByName"].values())
    print(f"\n{len(art['indexByName'])} per-name index betas ({n_rej} rejected -> prior); "
          f"evaluate with: -m backtest.benchmark_pack run --beta-table {args.out} "
          f"--pair-start <evalPairStart> --tag _b14_learned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
