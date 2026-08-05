"""Reproducible figure + macro pipeline for book Chapter 2 (LQD).

Book copy of Papers/lqd_paper/scripts/gen_figures.py; emits into
``Papers/book/figures/ch02/``.  Run from anywhere with the project venv:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch02\\gen_figures.py
    ... gen_figures.py --only fig_spy_node          # one figure
    ... gen_figures.py --only certification timing  # macro blocks only
    ... gen_figures.py --list                       # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
(real nodes are REBUILT from stored parameters, never refitted) plus
fixed-seed synthetic constructions.  Outputs: 14 ``figures/fig_*.pdf``,
``figures/paper_macros.tex`` (every quoted number), ``figures/MACROS.md``.
Deterministic except the two wall-clock timing macros blocks.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("VOLFIT_CALIB_WORKERS", "1")  # byte-identical serial fits

import matplotlib

matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).resolve().parent / "figlib"))

import figstyle  # noqa: E402

figstyle.setup()

import aliases  # noqa: E402
import audit  # noqa: E402
import data  # noqa: E402
import fig_audit  # noqa: E402
import incidents  # noqa: E402
import multistart  # noqa: E402
import fig_calendar  # noqa: E402
import fig_core  # noqa: E402
import fig_market  # noqa: E402
import fig_synth  # noqa: E402
import fig_tails  # noqa: E402
from macros import STORE  # noqa: E402

# Paper order F1..F14; values are zero-argument builders returning a summary.
FIGURES = {
    "fig_transport": fig_core.fig_transport,
    "fig_modes": fig_core.fig_modes,
    "fig_exact": fig_core.fig_exact,
    "fig_spy_gallery": fig_market.fig_spy_gallery,
    "fig_spy_node": fig_market.fig_spy_node,
    "fig_nvda_nodes": fig_market.fig_nvda_nodes,
    "fig_lqd_chart": fig_market.fig_lqd_chart,
    "fig_tails": fig_tails.fig_tails,
    "fig_lee": fig_tails.fig_lee,
    "fig_doublehump": fig_synth.fig_doublehump,
    "fig_order_control": fig_synth.fig_order_control,
    "fig_jacobian": fig_audit.fig_jacobian,
    "fig_calendar": fig_calendar.fig_calendar,
    "fig_butterfly": fig_audit.fig_butterfly,
}

# Macro-only blocks (no PDF output); "aliases" runs LAST — it re-emits the
# author-contract names from the values every earlier block stored.
MACRO_BLOCKS = {
    "snapshot": data.add_snapshot_macros,
    "certification": audit.certification,
    "timing": audit.timing,
    "ticket": audit.ticket,
    "incidents": incidents.incidents,
    "multistart": multistart.multistart,
    "aliases": aliases.aliases,
}

ALL_TARGETS = {**FIGURES, **MACRO_BLOCKS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", metavar="TARGET",
                        choices=sorted(ALL_TARGETS),
                        help="rebuild only these figures / macro blocks")
    parser.add_argument("--list", action="store_true",
                        help="list every target and exit")
    ns = parser.parse_args()

    if ns.list:
        for name in ALL_TARGETS:
            kind = "figure" if name in FIGURES else "macros"
            print(f"  {name:20s} [{kind}]")
        return 0

    targets = ns.only or list(ALL_TARGETS)
    start = time.perf_counter()
    print(f"Rebuilding slices from the frozen snapshot "
          f"(worst gap {data.verify_rebuild():.4f} bp) ...")
    for name in ALL_TARGETS:  # keep canonical order regardless of CLI order
        if name not in targets:
            continue
        t0 = time.perf_counter()
        summary = ALL_TARGETS[name]()
        print(f"  {name:20s} {time.perf_counter() - t0:6.1f}s  "
              f"{summary or 'done'}")
    count, tex_path = STORE.write()
    elapsed = time.perf_counter() - start
    pdfs = sorted(p.name for p in figstyle.FIG_DIR.glob("fig_*.pdf"))
    print(f"\n{len(pdfs)} figure PDFs in {figstyle.FIG_DIR}")
    print(f"{count} macros in {tex_path}")
    print(f"total {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
