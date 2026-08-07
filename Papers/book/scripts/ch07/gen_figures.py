"""Reproducible figure + macro pipeline for book Chapter 7 (early exercise).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch07\\gen_figures.py
    ... gen_figures.py --only fig_deam_bow        # one figure
    ... gen_figures.py --list                     # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
(raw dollar chains -- American-style -- plus per-node resolved forwards)
and the deterministic synthetic constructions of appendix 7.A.  No
randomness anywhere.
Outputs: ``figures/ch07/fig_*.pdf``, ``figures/ch07/ch07_macros.tex`` (every
number the chapter quotes), ``figures/ch07/MACROS.md``.  Fully deterministic.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("VOLFIT_CALIB_WORKERS", "1")  # byte-identical serial

import matplotlib

matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).resolve().parent / "figlib"))

import figstyle  # noqa: E402

figstyle.setup()

import fig_bow  # noqa: E402
import fig_escrow  # noqa: E402
import fig_gallery  # noqa: E402
import fig_lattice  # noqa: E402
import fig_map  # noqa: E402
import fig_root  # noqa: E402
import fig_wedge  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F7.
FIGURES = {
    "fig_deam_wedge": fig_wedge.fig_deam_wedge,
    "fig_deam_map": fig_map.fig_deam_map,
    "fig_deam_tree": fig_lattice.fig_deam_tree,
    "fig_deam_root": fig_root.fig_deam_root,
    "fig_deam_escrow": fig_escrow.fig_deam_escrow,
    "fig_deam_bow": fig_bow.fig_deam_bow,
    "fig_deam_gallery": fig_gallery.fig_deam_gallery,
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
