"""Freeze the LQD paper's real-data snapshot: SPY + NVDA, Massive feed, haircut fit.

In-process driver (no server, no process pool): fetch the two chains, calibrate
every lit node with the LQD model under the paper's pinned hyperparameters, and
export the surfaces JSON with embedded inputs so every figure in the paper can
be regenerated offline from the frozen artifact.

Run from the repo root with the Massive key in the environment (dot-source
restart.local.ps1 first):

    . .\restart.local.ps1
    .venv\Scripts\python.exe Papers\lqd_paper\scripts\fetch_snapshot.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Serial calibration: this driver never touches the worker pool, but pin it
# anyway so nothing downstream can spawn workers (must precede volfit imports).
os.environ.setdefault("VOLFIT_CALIB_WORKERS", "1")

from volfit.api import export, workflow  # noqa: E402
from volfit.api.quality import build_quality_report  # noqa: E402
from volfit.api.schemas import FitSettings  # noqa: E402
from volfit.api.state import AppState  # noqa: E402
from volfit.data.massive import MassiveProvider  # noqa: E402

TICKERS = ["SPY", "NVDA"]
FIT_MODE = "haircut"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    api_key = os.environ.get("VOLFIT_MASSIVE_KEY", "").strip()
    if not api_key:
        print("VOLFIT_MASSIVE_KEY is not set - dot-source restart.local.ps1 first.")
        return 2

    provider = MassiveProvider(
        TICKERS,
        api_key=api_key,
        ws_url=os.environ.get("VOLFIT_MASSIVE_WS_URL") or None,
        flat_store=None,  # live snapshot only; past-day history not needed
    )
    # store_path=None: no persisted settings leak in - the paper's recipe is
    # exactly what is pinned below, and the manifest records all of it.
    state = AppState(
        date.today(),
        providers={"massive": provider},
        active_source="massive",
        store_path=None,
        gated=True,
    )

    # The paper's pinned recipe: LQD, Legendre order 16 (production default),
    # logistic endpoint chart, 0.5-vol-point haircut band. Everything else at
    # code defaults; the export manifest stamps the full FitSettings.
    state.set_fit_settings(
        FitSettings(model="lqd", nOrder=16, lqdCoords="logistic", haircut=0.005)
    )
    # autoCalibrate off: fetch_options must NOT kick a background pooled
    # calibration - we calibrate inline per ticker below. LV surface is out of
    # scope for this paper; calendar coupling stays on (production default).
    state.set_options(
        state.options().model_copy(
            update={"autoCalibrate": False, "localVolEnabled": False, "enforceCalendar": True}
        )
    )
    state.note_fit_mode(FIT_MODE)  # manifest fitMode when export falls back

    print(f"Fetching {TICKERS} from Massive (delayed) ...")
    fetched = workflow.fetch_options(state, TICKERS, FIT_MODE)
    missing = [t for t in TICKERS if t not in fetched.tickers]
    if missing:
        print(f"FETCH FAILED for {missing}; got {fetched.tickers}. Aborting.")
        return 1
    for t in fetched.tickers:
        print(f"  {t}: spot {fetched.spots.get(t)}")

    for t in fetched.tickers:
        n = workflow.calibrate_ticker(state, t, FIT_MODE)
        print(f"Calibrated {t}: {n} nodes ({FIT_MODE}, LQD-16)")

    report = build_quality_report(state, FIT_MODE)
    s = report.summary
    print(
        f"Quality: fitted {s.fitted}/{s.litNodes} lit nodes, ready {s.readyNodes}, "
        f"median rms {s.medianRmsBp:.1f}bp, worst {s.worstRmsBp:.1f}bp"
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    # project_wings=False: the paper charts the fitted LQD slices themselves;
    # the publish-time wing projection is a downstream feature (and on this
    # after-hours delayed book it manufactures a calendar crossing on SPY).
    try:
        surf = export.build_surface_export(
            state,
            fit_mode=FIT_MODE,
            tickers=TICKERS,
            project_wings=False,
            require_clean=True,
            include_inputs=True,
        )
        out = DATA_DIR / f"lqd_paper_snapshot_{stamp}.json"
    except export.PublishBlockedError as exc:
        # Draft export keeps the paper unblocked; defects stay stamped per node.
        print(f"Publish blocked ({exc}); exporting DRAFT artifact instead.")
        surf = export.build_surface_export(
            state,
            fit_mode=FIT_MODE,
            tickers=TICKERS,
            project_wings=False,
            require_clean=False,
            include_inputs=True,
        )
        out = DATA_DIR / f"lqd_paper_snapshot_{stamp}_DRAFT.json"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(surf.model_dump_json(), encoding="utf-8")
    m = surf.manifest
    print(f"Wrote {out}  ({out.stat().st_size / 1024:.0f} KB)")
    fs = dict(m.fitSettings)
    print(
        f"Manifest: source={m.source} fitMode={m.fitMode} nOrder={fs.get('nOrder')} "
        f"lqdCoords={fs.get('lqdCoords')} fittedNodes={m.fittedNodes}"
    )
    for tk in surf.tickers:
        worst = max((nd.quality.rmsBp for nd in tk.nodes), default=0.0)
        print(f"  {tk.ticker}: {len(tk.nodes)} nodes, spot {tk.spot}, worst rmsBp {worst:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
