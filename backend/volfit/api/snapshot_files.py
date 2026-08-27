"""Snapshot FILES — quotes + prevailing calibrations as a data source (wave 3, A2).

Bundle ``volfit-snapshot/1``::

    { "schema", "savedAt", "asOf", "source": {id, label}, "app": {version},
      "manifest": {referenceDate, fitMode, tickers},
      "tickers": [ { "ticker", "spot", "timestamp", "exerciseStyle",
                     "chain": <export_inputs.ExportChain>,          # every fetched quote
                     "forwards": [{expiry, forward, discount, source}],
                     "calibrations": [ { "expiry", "fitMode", "model",
                                         "lqd": {L, R, a, alphaL, alphaR},
                                         "display": {model, params, handles, …} | null,
                                         "diagnostics": {cost, nEvaluations, success, maxIvError},
                                         "provenance" } ] } ] }

* ``export_snapshot`` reads the CACHED chains and COMMITTED fits (never
  fetches, never refits): the chain exactly as fetched, plus each calibrated
  node's LQD backbone params, displayed-overlay params (the same
  ``dataclasses.asdict`` dump the prior snapshots use) and scalar diagnostics.
* ``import_snapshot`` validates the envelope, loads the chains into the
  ``file`` data source (volfit.data.file.FileProvider — registered on first
  use, later files union in), switches the app to it (a chain-cache reset),
  points the universe at the file's tickers with their embedded expiries
  selected, then REINSTALLS every embedded calibration as the COMMITTED fit:
  PreparedQuotes re-derived from the embedded chain by the standard prep
  path, ``CalibrationResult`` rebuilt from the params (``build_slice`` is
  deterministic, so the slice is byte-identical), the overlay ``DisplayFit``
  rebuilt from its params, all committed through ``service.commit_record``
  with provenance ``"loaded"`` (Quality's model column + the fit chip show
  it). Calibrate then refits from the embedded quotes under the live Options.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

import numpy as np

from volfit import __version__
from volfit.api import service
from volfit.api.export_inputs import export_chain
from volfit.api.state import FitRecord
from volfit.data.file import SOURCE_ID, FileProvider, chain_from_doc
from volfit.models.diagnostics import SliceHandles
from volfit.models.display import DisplayFit
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import CalibrationResult
from volfit.models.lqd.quadrature import build_slice
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv
from volfit.models.svi_jw.svi import RawSVI

SNAPSHOT_SCHEMA = "volfit-snapshot/1"
_FAMILY, _MAJOR = SNAPSHOT_SCHEMA.split("/")


class SnapshotFormatError(ValueError):
    """Not a snapshot file this server can load (→ HTTP 422)."""


# ------------------------------------------------------------------ export
def export_snapshot(state, tickers: list[str] | None = None, fit_mode: str | None = None) -> dict:
    """The bundle for the active universe's LOADED chains (see module doc)."""
    mode = fit_mode or state.last_fit_mode
    chosen = [t for t in state.active_tickers() if not tickers or t in tickers]
    out_tickers = []
    for ticker in chosen:
        snap = state.loaded_snapshot(ticker)
        if snap is None or not snap.quotes:
            continue
        out_tickers.append({
            "ticker": ticker,
            "spot": float(snap.spot),
            "timestamp": snap.timestamp.isoformat(),
            "exerciseStyle": snap.exercise_style,
            "chain": export_chain(snap).model_dump(),
            "forwards": _forwards_doc(state, ticker, snap),
            "calibrations": _calibrations_doc(state, ticker),
        })
    stamp = max((t["timestamp"] for t in out_tickers), default=None)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "savedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "asOf": stamp,
        "source": {"id": state.active_source, "label": _source_label(state)},
        "app": {"version": __version__},
        "manifest": {
            "referenceDate": state.reference_date.isoformat(),
            "fitMode": mode,
            "tickers": [t["ticker"] for t in out_tickers],
        },
        "tickers": out_tickers,
    }


def _source_label(state) -> str:
    from volfit.api.datasource import source_label

    return source_label(state.active_source, state.provider)


def _forwards_doc(state, ticker: str, snap) -> list[dict]:
    out = []
    for expiry in snap.expiries():
        try:
            f = state.resolved_forward(ticker, expiry)
        except Exception:  # noqa: BLE001 — a forward that cannot resolve is simply absent
            continue
        out.append({"expiry": expiry.isoformat(), "forward": float(f.forward),
                    "discount": float(f.discount), "source": f.source})
    return out


def _calibrations_doc(state, ticker: str) -> list[dict]:
    """Every COMMITTED fit of the ticker (all fit modes), oldest expiry first."""
    out = []
    with state._lock:
        ptrs = {k: v for k, v in state._calibrated.items() if k[0] == ticker}
    for (_, iso, mode), (key, _spot) in sorted(ptrs.items()):
        record = state.get_fit(key)
        if record is None:
            continue
        p = record.result.params
        out.append({
            "expiry": iso,
            "fitMode": mode,
            "model": record.display.model if record.display is not None else "lqd",
            "lqd": {"L": float(p.L), "R": float(p.R), "a": np.asarray(p.a, dtype=float).tolist(),
                    "alphaL": float(p.alpha_left), "alphaR": float(p.alpha_right)},
            "display": _display_doc(record.display),
            "diagnostics": {
                "cost": float(record.result.cost),
                "nEvaluations": int(record.result.n_evaluations),
                "success": bool(record.result.success),
                "maxIvError": float(record.result.max_iv_error),
            },
            "provenance": getattr(record, "provenance", "fit"),
        })
    return out


def _display_doc(display: DisplayFit | None) -> dict | None:
    if display is None:
        return None
    return {
        "model": display.model,
        "params": _jsonable(dataclasses.asdict(display.slice)),
        "handles": dataclasses.asdict(display.handles),
        "varSwapW": float(display.var_swap_w),
        "leeLeft": float(display.lee_left),
        "leeRight": float(display.lee_right),
        "maxIvError": float(display.max_iv_error),
        "bellyRepaired": bool(display.belly_repaired),
    }


def _jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


# ------------------------------------------------------------------ import
def validate_bundle(body) -> dict:
    if not isinstance(body, dict):
        raise SnapshotFormatError("snapshot file must be a JSON object")
    tag = body.get("schema")
    if not isinstance(tag, str) or "/" not in tag:
        raise SnapshotFormatError(f"missing or malformed 'schema' tag (expected '{SNAPSHOT_SCHEMA}')")
    family, _, major = tag.partition("/")
    if family != _FAMILY:
        raise SnapshotFormatError(f"not a snapshot file: schema {tag!r} (expected '{SNAPSHOT_SCHEMA}')")
    if major != _MAJOR:
        raise SnapshotFormatError(f"snapshot schema {tag!r} is not supported (supports '{SNAPSHOT_SCHEMA}')")
    tickers = body.get("tickers")
    if not isinstance(tickers, list) or not tickers:
        raise SnapshotFormatError("snapshot file carries no tickers")
    for t in tickers:
        if not isinstance(t, dict) or not t.get("ticker") or not isinstance(t.get("chain"), dict):
            raise SnapshotFormatError("malformed ticker entry (needs 'ticker' + 'chain')")
    return body


def import_snapshot(state, body, name: str) -> dict:
    """Load a bundle as the ``file`` data source and reinstall its fits."""
    bundle = validate_bundle(body)
    chains = {}
    for t in bundle["tickers"]:
        try:
            chains[str(t["ticker"]).upper()] = chain_from_doc(
                str(t["ticker"]).upper(), float(t.get("spot", 0.0)),
                str(t.get("timestamp") or bundle.get("asOf") or datetime.now().isoformat()),
                t["chain"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotFormatError(f"chain of {t.get('ticker')!r} could not be read: {exc}") from exc
    as_of = max(c.timestamp for c in chains.values())
    provider = state.file_provider()
    provider.load(name, chains, as_of)
    state.set_active_source(SOURCE_ID)
    state.set_active_tickers(provider.list_tickers())
    installed, failed = 0, []
    for t in bundle["tickers"]:
        ticker = str(t["ticker"]).upper()
        snap = chains[ticker]
        state.set_expiries(ticker, snap.expiries())
        state.ensure_chain(ticker)
        for cal in t.get("calibrations") or []:
            try:
                _install_calibration(state, ticker, cal)
                installed += 1
            except Exception as exc:  # noqa: BLE001 — one bad fit never blocks the file
                failed.append(f"{ticker} {cal.get('expiry')}: {exc}")
    state.log_event("snapshot_import", payload={"name": name, "tickers": len(chains), "fits": installed})
    return {
        "source": SOURCE_ID,
        "label": provider.label,
        "asOf": as_of.isoformat(),
        "tickers": sorted(chains),
        "calibrations": installed,
        "failed": failed,
    }


def _install_calibration(state, ticker: str, cal: dict) -> None:
    iso = date.fromisoformat(str(cal["expiry"])).isoformat()
    mode = str(cal.get("fitMode") or "mid")
    expiry = state.resolve_expiry(ticker, iso)
    prepared = service.prepared_quotes(state, ticker, expiry)
    lq = cal["lqd"]
    params = LQDParams(
        L=float(lq["L"]), R=float(lq["R"]), a=np.asarray(lq.get("a", []), dtype=float),
        alpha_left=float(lq.get("alphaL", 0.0)), alpha_right=float(lq.get("alphaR", 0.0)),
    )
    d = cal.get("diagnostics") or {}
    result = CalibrationResult(
        params=params, slice=build_slice(params), cost=float(d.get("cost", 0.0)),
        n_evaluations=int(d.get("nEvaluations", 0)), success=bool(d.get("success", True)),
        max_iv_error=float(d.get("maxIvError", 0.0)),
    )
    display = _display_from_doc(cal.get("display"))
    record = FitRecord(prepared=prepared, result=result, display=display, provenance="loaded")
    service.commit_record(state, ticker, iso, mode, record, None)


def _display_from_doc(doc: dict | None) -> DisplayFit | None:
    if not doc:
        return None
    model = str(doc["model"])
    p = dict(doc["params"])
    if model == "svi":
        slice_ = RawSVI(**{k: float(p[k]) for k in ("a", "b", "rho", "m", "sigma")})
    elif model in ("sigmoid", "mcs"):
        cores = tuple(HatCore(**{k: float(c[k]) for k in ("alpha", "c", "h", "kappa")}) for c in p.get("cores", []))
        slice_ = MultiCoreSiv(
            **{k: float(p[k]) for k in ("v0", "s0", "k0", "z0", "kappa_p", "kappa_c", "sigma_ref", "t")},
            cores=cores,
        )
    else:
        raise SnapshotFormatError(f"unknown displayed model {model!r}")
    h = doc.get("handles") or {}
    return DisplayFit(
        model=model, slice=slice_,
        handles=SliceHandles(atm_vol=float(h.get("atm_vol", 0.0)), skew=float(h.get("skew", 0.0)),
                             curvature=float(h.get("curvature", 0.0))),
        var_swap_w=float(doc.get("varSwapW", 0.0)), lee_left=float(doc.get("leeLeft", 0.0)),
        lee_right=float(doc.get("leeRight", 0.0)), max_iv_error=float(doc.get("maxIvError", 0.0)),
        belly_repaired=bool(doc.get("bellyRepaired", False)),
    )
