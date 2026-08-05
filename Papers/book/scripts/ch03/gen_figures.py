"""Reproducible figure + macro pipeline for book Chapter 3 (SVI-JW / MCS).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch03\\gen_figures.py
    ... gen_figures.py --only fig_cmp_node      # one figure
    ... gen_figures.py --list                   # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
plus deterministic synthetic constructions (no randomness anywhere).
Outputs: ``figures/ch03/fig_*.pdf``, ``figures/ch03/ch03_macros.tex`` (every
number the chapter quotes), ``figures/ch03/MACROS.md``.  Fully deterministic.
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

import fig_cmp  # noqa: E402
import fig_mcs  # noqa: E402
import fig_svi  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F10.
FIGURES = {
    "fig_svi_zoo": fig_svi.fig_svi_zoo,
    "fig_svi_handles": fig_svi.fig_svi_handles,
    "fig_svi_lee": fig_svi.fig_svi_lee,
    "fig_svi_vogt": fig_svi.fig_svi_vogt,
    "fig_svi_stratum": fig_svi.fig_svi_stratum,
    "fig_svi_structural": fig_svi.fig_svi_structural,
    "fig_mcs_mechanism": fig_mcs.fig_mcs_mechanism,
    "fig_cmp_mixture": fig_cmp.fig_cmp_mixture,
    "fig_cmp_node": fig_cmp.fig_cmp_node,
    "fig_cmp_gallery": fig_cmp.fig_cmp_gallery,
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
