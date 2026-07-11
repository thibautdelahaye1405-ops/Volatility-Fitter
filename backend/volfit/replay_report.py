"""One-command replay of a published surface (governance kernel, R1 item 8).

The acceptance criterion of roadmap item 3.5: *given any published surface
point, reproduce it from stored inputs and its manifest after a process
restart.* This tool loads a publish manifest from the app store, rebuilds a
FRESH AppState from the stored chain snapshots + settings + forward
policies, re-calibrates exactly the published nodes, re-exports with the
same wing-projection flag, and diffs every published curve point against
the stored artifact.

Run (from backend\\)::

    python -m volfit.replay_report [manifest_id|latest] [--db path] [--tol 1e-7]

``--db`` defaults to the VOLFIT_DB environment variable (what the app runs
with). Exit code 0 = every point within tolerance, 1 otherwise.

Fidelity: manifests capture session quote edits, var-swap quotes and
active-prior content (R1 item 9 closed the v0 gaps), and this tool restores
them before recalibrating — edited/anchored surfaces replay exactly.
Documented remaining limits (surfaced in the report when present): a node
published STALE was frozen at older inputs than the manifest captures, so
it diffs by construction; legacy v0 manifests carry only edit/prior COUNTS,
so their edited/anchored nodes keep a stated tolerance; a publish made with
the ACTIVE observation filter is anchored to a Kalman prediction state that
no longer exists at replay time; the LV grid is stored in the artifact but
not re-fit here.
"""

from __future__ import annotations

import argparse
import os
from datetime import date

import numpy as np

from volfit.data import governance
from volfit.data.provider import OptionChainProvider
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot


class _StoredChains(OptionChainProvider):
    """Serves the manifest's persisted snapshots from memory."""

    def __init__(self, chains: dict[str, ChainSnapshot]) -> None:
        self._chains = chains

    def list_tickers(self) -> list[str]:
        return list(self._chains)

    def available_expiries(self, ticker: str):
        return self._chains[ticker].expiries()

    def fetch_chain(self, ticker, expiries=None, as_of=None) -> ChainSnapshot:
        ch = self._chains[ticker]
        if expiries:
            want = set(expiries)
            kept = [q for q in ch.quotes if q.expiry in want]
            return ChainSnapshot(
                ticker=ch.ticker, spot=ch.spot, timestamp=ch.timestamp,
                quotes=kept, exercise_style=ch.exercise_style,
                zero_carry=ch.zero_carry, tick_size=ch.tick_size,
                settlement=ch.settlement,
            )
        return ch


def replay(db_path, manifest_id: str = "latest", tol: float = 1e-7) -> dict:
    """Rebuild one published surface and diff it; returns the report dict."""
    from volfit.api import service
    from volfit.api.export import build_surface_export
    from volfit.api.schemas import (
        FitSettings,
        ForwardPolicy,
        MarketSettings,
        OptionsSettings,
    )
    from volfit.api.state import AppState

    with VolStore(db_path) as store:
        if manifest_id == "latest":
            manifest_id = governance.latest_manifest_id(store)
            if manifest_id is None:
                raise SystemExit("no publish manifests in this store")
        row = governance.load_manifest(store, manifest_id)
        if row is None:
            raise SystemExit(f"unknown manifest id {manifest_id!r}")
        doc = row["doc"]
        snapshots = {
            tk: store.load_snapshot(int(sid))
            for tk, sid in doc["snapshotIds"].items()
        }
    artifact = row["artifact"]
    if artifact is None:
        raise SystemExit(
            "artifact pruned by retention — replay needs the stored artifact"
        )

    # A FRESH state from stored inputs only (no store: replay never publishes).
    state = AppState(
        date.fromisoformat(doc["referenceDate"]), provider=_StoredChains(snapshots)
    )
    state.set_fit_settings(FitSettings(**doc["fitSettings"]))
    state.set_options(OptionsSettings(**doc["options"]))
    for tk, ms in doc.get("marketSettings", {}).items():
        state.set_market_settings(tk, MarketSettings(**ms))
    for tk, pols in doc.get("forwardPolicies", {}).items():
        for iso, pol in pols.items():
            state.set_forward_policy(tk, iso, ForwardPolicy(**pol))
    # Replay fidelity (R1 item 9): restore the captured session quote edits,
    # var-swap quotes and active priors so edited/anchored fits reproduce
    # exactly. Legacy v0 manifests lack these keys (see _fidelity_notes).
    for tk, per in doc.get("sessionEdits", {}).items():
        for iso, sdoc in per.items():
            state.session((tk, iso)).load_doc(sdoc)
    for tk, per in doc.get("varSwapQuotes", {}).items():
        for iso, vdoc in per.items():
            state.varswap_session((tk, iso)).load_doc(vdoc)
    if doc.get("activePriorContent"):
        from volfit.api.schemas_prior import PriorSurfaceSnapshot

        for tk, blob in doc["activePriorContent"].items():
            state.set_active_prior(
                tk,
                PriorSurfaceSnapshot.model_validate(blob),
                doc.get("activePriorSources", {}).get(tk, "saved"),
            )
    for tk, isos in doc["nodes"].items():
        for iso in isos:
            service.calibrate_node(state, tk, iso, doc["fitMode"])
    rebuilt = build_surface_export(
        state, doc["fitMode"], list(doc["nodes"]),
        project_wings=doc.get("projectWings", True),
    )

    stored_nodes = {
        (t["ticker"], n["expiry"]): n
        for t in artifact["tickers"]
        for n in t["nodes"]
    }
    rows, worst = [], 0.0
    for t in rebuilt.tickers:
        for n in t.nodes:
            stored = stored_nodes.pop((t.ticker, n.expiry), None)
            if stored is None or len(stored["curve"]) != len(n.curve):
                rows.append({"ticker": t.ticker, "expiry": n.expiry,
                             "maxIvDiff": float("inf"), "note": "grid mismatch"})
                worst = float("inf")
                continue
            diff = float(
                np.max(np.abs(np.array([p.iv for p in n.curve])
                              - np.array([p["iv"] for p in stored["curve"]])))
            )
            worst = max(worst, diff)
            rows.append({"ticker": t.ticker, "expiry": n.expiry, "maxIvDiff": diff})
    for (tk, iso) in stored_nodes:  # published but not reproduced
        rows.append({"ticker": tk, "expiry": iso, "maxIvDiff": float("inf"),
                     "note": "missing on replay"})
        worst = float("inf")

    return {
        "manifestId": manifest_id,
        "state": row["state"],
        "publishedAt": row["ts"],
        "nodes": rows,
        "worstIvDiff": worst,
        "tolerance": tol,
        "ok": worst <= tol,
        "fidelityNotes": _fidelity_notes(doc),
    }


def _fidelity_notes(doc: dict) -> list[str]:
    """Documented fidelity limits of one manifest, empty when replay is exact.

    Content-capturing manifests (R1 item 9: ``sessionEdits`` /
    ``activePriorContent`` present, even if empty) restore edits and priors, so
    the legacy count-based notes apply only to v0 manifests that lack the keys.
    A publish made with the ACTIVE observation filter is anchored to a Kalman
    prediction state that predates the published fits and is not recoverable
    post-hoc — always noted."""
    notes = []
    if doc.get("staleNodes", 0):
        notes.append(
            f"{doc['staleNodes']} published node(s) were STALE — frozen at "
            "older inputs than the manifest captures, diffs there are expected"
        )
    if "sessionEdits" not in doc and doc.get("editedNodes", 0):
        notes.append(
            f"{doc['editedNodes']} node(s) had session quote edits "
            "(legacy manifest, content not captured — diffs there are expected)"
        )
    if "activePriorContent" not in doc and doc.get("activePriors", 0):
        notes.append(
            f"{doc['activePriors']} ticker(s) had an active prior "
            "(legacy manifest, content not captured)"
        )
    if doc.get("options", {}).get("observationFilterMode") == "active":
        notes.append(
            "published with the ACTIVE observation filter — the MAP prediction "
            "prior is not replayable, read diffs against a stated tolerance"
        )
    return notes


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay a published surface.")
    ap.add_argument("manifest", nargs="?", default="latest")
    ap.add_argument("--db", default=os.environ.get("VOLFIT_DB"))
    ap.add_argument("--tol", type=float, default=1e-7)
    args = ap.parse_args()
    if not args.db:
        raise SystemExit("no store: pass --db or set VOLFIT_DB")
    report = replay(args.db, args.manifest, args.tol)
    print(f"manifest {report['manifestId'][:16]}…  published {report['publishedAt']}"
          f"  state={report['state']}")
    for note in report["fidelityNotes"]:
        print(f"  NOTE: {note}")
    for r in report["nodes"]:
        flag = "" if r["maxIvDiff"] <= args.tol else "  <-- DIFF"
        note = f"  ({r['note']})" if r.get("note") else ""
        print(f"  {r['ticker']:6s} {r['expiry']}  max|dIV| = "
              f"{r['maxIvDiff']:.3e}{note}{flag}")
    verdict = "REPLAY OK" if report["ok"] else "REPLAY DIVERGED"
    print(f"{verdict}: worst {report['worstIvDiff']:.3e} vs tol {args.tol:g} "
          f"over {len(report['nodes'])} node(s)")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
