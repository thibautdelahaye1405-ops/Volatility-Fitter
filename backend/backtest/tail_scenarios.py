"""Tail-exponent scenario comparison (generalized-tails arc Phase 3).

Book ch. 2 §"Choose the tail class outside the optimizer", policy 3 — the
preferred practice: calibrate the SAME maturity stack under a small grid of
stated tail-exponent scenarios and report the downstream deltas, because no
finite strike strip identifies the exponent while the moment domain, wing
class and tail-sensitive prices all flip with it. The instrument here:

  per (ticker, expiry, scenario): fit RMS (indistinguishability on the
  strip), var-swap vol, moment limits r+*/r-* (eq. momentboundaries; None =
  every moment finite), OTM tail digitals P(X > k) / P(X < -k), RR25/BF25
  packages — plus deltas against the exponential baseline.

Input: a surfaces-export artifact WITH embedded inputs (GET /export/surfaces
— the self-contained JSON the app publishes; the standing reference fixture
tmp\\volfit_surfaces_*.json is one), or any per-ticker {t, k, w} stack via
``run_scenarios`` directly. Output: JSON + a small HTML table under
``results/tail_scenarios/``.

Run (from backend\\)::

    python -m backtest.tail_scenarios run --artifact ..\\tmp\\volfit_surfaces_20260718_1324.json
    python -m backtest.tail_scenarios run --artifact <path> --scenarios exponential,gaussian
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from html import escape

import numpy as np
from scipy.special import expit

from volfit.calib.calendar import calendar_floor_targets
from volfit.calib.operators import evaluate_operators
from volfit.models.lqd.basis import endpoint_scales
from volfit.models.lqd.calibrate import calibrate_slice

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "tail_scenarios")

#: The named scenario grid (alpha_left, alpha_right) — the book's three
#: anchors plus the equity convention "keep the crash side exponential".
SCENARIOS: dict[str, tuple[float, float]] = {
    "exponential": (0.0, 0.0),
    "light_right": (0.0, 0.25),
    "intermediate": (0.25, 0.25),
    "gaussian": (0.5, 0.5),
}
BASELINE = "exponential"

#: Tail digital probes (log-moneyness): P(X > k) on the right, P(X < -k)
#: on the left.
DIGITAL_KS = (0.25, 0.5)


@dataclass(frozen=True)
class SliceQuotes:
    """One expiry's fit inputs (total variance at log-moneyness)."""

    expiry: str
    t: float
    k: np.ndarray
    w: np.ndarray


def artifact_stacks(doc: dict) -> dict[str, list[SliceQuotes]]:
    """Per-ticker maturity stacks from a surfaces-export artifact.

    Uses each node's EMBEDDED prepared quotes (k, ivMid) at the node's
    variance time tau — the exact inputs the published fits saw. Nodes
    exported without inputs (inputs=false) are skipped.
    """
    stacks: dict[str, list[SliceQuotes]] = {}
    for tk in doc.get("tickers", []):
        rows: list[SliceQuotes] = []
        for node in tk.get("nodes", []):
            inputs = node.get("inputs")
            if not inputs or not inputs.get("prepared"):
                continue
            cols = {name: i for i, name in enumerate(inputs["preparedColumns"])}
            data = np.asarray(inputs["prepared"], dtype=float)
            k = data[:, cols["k"]]
            iv = data[:, cols["ivMid"]]
            tau = float(node["tau"])
            rows.append(SliceQuotes(
                expiry=str(node["expiry"]), t=tau, k=k, w=iv * iv * tau))
        if rows:
            stacks[str(tk["ticker"])] = sorted(rows, key=lambda s: s.t)
    return stacks


def _slice_metrics(fit, sq: SliceQuotes) -> dict:
    """Downstream numbers the tail class actually moves (module docstring)."""
    sl, p = fit.slice, fit.params
    a_l, a_r = endpoint_scales(p)
    iv_model = np.sqrt(np.maximum(sl.implied_w(sq.k), 1e-12) / sq.t)
    iv_quote = np.sqrt(sq.w / sq.t)
    digitals: dict[str, float] = {}
    for kk in DIGITAL_KS:
        z = sl.strike_to_z(np.array([kk, -kk]))
        digitals[f"P(X>{kk})"] = float(expit(-z[0]))
        digitals[f"P(X<-{kk})"] = float(expit(z[1]))
    pkgs = evaluate_operators(sl.implied_w, sq.t, ["RR25", "BF25"])
    return {
        "rmsBp": float(np.sqrt(np.mean((iv_model - iv_quote) ** 2)) * 1e4),
        "varSwapVol": float(np.sqrt(max(sl.var_swap_strike(), 0.0) / sq.t)),
        # eq. momentboundaries: last finite moments of Y beyond/below the
        # mean; None = unbounded (every moment finite on that side).
        "momentPlus": None if p.alpha_right > 0.0 else 1.0 / a_r - 1.0,
        "momentMinus": None if p.alpha_left > 0.0 else 1.0 / a_l,
        "digitals": digitals,
        "RR25": float(pkgs["RR25"]),
        "BF25": float(pkgs["BF25"]),
    }


def run_scenarios(
    stacks: dict[str, list[SliceQuotes]],
    scenarios: dict[str, tuple[float, float]] | None = None,
    n_order: int = 8,
) -> dict:
    """Fit every stack under every scenario (sequential fits with the ledger
    calendar floor chained near -> far, the production shape) and tabulate
    per-node metrics + deltas vs the exponential baseline."""
    scenarios = SCENARIOS if scenarios is None else scenarios
    report: dict = {"scenarios": {n: list(a) for n, a in scenarios.items()},
                    "baseline": BASELINE, "nOrder": n_order, "tickers": {}}
    for ticker, stack in stacks.items():
        per_scenario: dict[str, list[dict]] = {}
        for name, (al, ar) in scenarios.items():
            rows: list[dict] = []
            prev = None
            for sq in stack:
                cal_z = cal_floor = None
                if prev is not None:
                    cal_z, cal_floor = calendar_floor_targets(prev)
                fit = calibrate_slice(
                    sq.k, sq.w, t=sq.t, n_order=n_order, coords="logistic",
                    calendar_z=cal_z, calendar_floor=cal_floor,
                    alpha_left=al, alpha_right=ar,
                )
                prev = fit.slice
                rows.append({"expiry": sq.expiry, "t": sq.t,
                             **_slice_metrics(fit, sq)})
            per_scenario[name] = rows
        base = {r["expiry"]: r for r in per_scenario.get(BASELINE, [])}
        for name, rows in per_scenario.items():
            for r in rows:
                b = base.get(r["expiry"])
                if b is None or name == BASELINE:
                    continue
                r["deltas"] = {
                    "varSwapVolBp": (r["varSwapVol"] - b["varSwapVol"]) * 1e4,
                    "rmsBp": r["rmsBp"] - b["rmsBp"],
                    "RR25Bp": (r["RR25"] - b["RR25"]) * 1e4,
                    "BF25Bp": (r["BF25"] - b["BF25"]) * 1e4,
                    "digitals": {
                        key: r["digitals"][key] - b["digitals"][key]
                        for key in r["digitals"]
                    },
                }
        report["tickers"][ticker] = per_scenario
    return report


def render_html(report: dict) -> str:
    """One compact table per ticker: rows = expiry x metric, cols = scenario."""
    parts = [
        "<html><head><meta charset='utf-8'><title>Tail scenarios</title>",
        "<style>body{font-family:system-ui;margin:24px}table{border-collapse:"
        "collapse;margin:12px 0}td,th{border:1px solid #ccc;padding:3px 9px;"
        "text-align:right}th{background:#f0f2f5}td.l{text-align:left}</style>",
        "</head><body><h2>Tail-exponent scenario comparison</h2>",
        "<p>Same stack, same quotes, different stated tail class "
        "(book ch. 2 scenario policy). None = every moment finite.</p>",
    ]
    names = list(report["scenarios"])
    for ticker, per_scenario in report["tickers"].items():
        parts.append(f"<h3>{escape(ticker)}</h3><table><tr><th>expiry</th>"
                     "<th>metric</th>" + "".join(f"<th>{escape(n)}</th>" for n in names)
                     + "</tr>")
        expiries = [r["expiry"] for r in per_scenario[names[0]]]
        metrics = ["rmsBp", "varSwapVol", "momentPlus", "momentMinus", "RR25", "BF25"]
        for expiry in expiries:
            rows = {n: next(r for r in per_scenario[n] if r["expiry"] == expiry)
                    for n in names}
            for metric in metrics:
                cells = "".join(
                    f"<td>{'∞' if rows[n][metric] is None else f'{rows[n][metric]:.4g}'}</td>"
                    for n in names
                )
                parts.append(f"<tr><td class='l'>{escape(expiry)}</td>"
                             f"<td class='l'>{metric}</td>{cells}</tr>")
            for key in rows[names[0]]["digitals"]:
                cells = "".join(f"<td>{rows[n]['digitals'][key]:.3e}</td>" for n in names)
                parts.append(f"<tr><td class='l'>{escape(expiry)}</td>"
                             f"<td class='l'>{escape(key)}</td>{cells}</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["run"])
    ap.add_argument("--artifact", required=True,
                    help="surfaces-export JSON with embedded inputs")
    ap.add_argument("--scenarios", default=None,
                    help="comma-separated subset of " + ",".join(SCENARIOS))
    ap.add_argument("--n-order", type=int, default=8)
    args = ap.parse_args(argv)

    with open(args.artifact, encoding="utf-8") as fh:
        doc = json.load(fh)
    stacks = artifact_stacks(doc)
    if not stacks:
        raise SystemExit("artifact carries no embedded inputs (export with inputs=true)")
    chosen = SCENARIOS
    if args.scenarios:
        chosen = {n: SCENARIOS[n] for n in args.scenarios.split(",")}
    report = run_scenarios(stacks, chosen, n_order=args.n_order)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    json_path = os.path.join(RESULTS_DIR, "tail_scenarios.json")
    html_path = os.path.join(RESULTS_DIR, "tail_scenarios.html")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(report))
    print(f"wrote {json_path}\nwrote {html_path}")


if __name__ == "__main__":
    main()
