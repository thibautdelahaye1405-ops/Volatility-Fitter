"""Reproducible figure + macro pipeline for book Chapter 4 (local volatility).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch04\\gen_figures.py
    ... gen_figures.py --only fig_lv_ratio       # one figure
    ... gen_figures.py --list                    # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
plus deterministic synthetic constructions (no randomness anywhere).
Outputs: ``figures/ch04/fig_*.pdf``, ``figures/ch04/ch04_macros.tex`` (every
number the chapter quotes), ``figures/ch04/MACROS.md``.  Fully deterministic.
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

import fig_examples  # noqa: E402
import fig_identify  # noqa: E402
import fig_lattice  # noqa: E402
import fig_ratio  # noqa: E402
import fig_sheet  # noqa: E402
import fig_wrongway  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F10.
FIGURES = {
    "fig_lv_ratio": fig_ratio.fig_lv_ratio,
    "fig_lv_wrongway": fig_wrongway.fig_lv_wrongway,
    "fig_lv_sheet": fig_sheet.fig_lv_sheet,
    "fig_lv_basis": fig_sheet.fig_lv_basis,
    "fig_lv_monotone": fig_lattice.fig_lv_monotone,
    "fig_lv_identify": fig_identify.fig_lv_identify,
    "fig_lv_influence": fig_identify.fig_lv_influence,
    "fig_lv_recovery": fig_examples.fig_lv_recovery,
    "fig_lv_fit": fig_examples.fig_lv_fit,
    "fig_lv_rms": fig_examples.fig_lv_rms,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", metavar="TARGET",
                        choices=sorted(FIGURES),
                        help="rebuild only these figures")
    parser.add_argument("--list", action="store_true",
                        help="list every target and exit")
    ns = parser.parse_args()

    if ns.list:
        for name in FIGURES:
            print(f"  {name}")
        return 0

    targets = ns.only or list(FIGURES)
    start = time.perf_counter()
    for name in FIGURES:  # keep canonical order regardless of CLI order
        if name not in targets:
            continue
        t0 = time.perf_counter()
        summary = FIGURES[name]()
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
