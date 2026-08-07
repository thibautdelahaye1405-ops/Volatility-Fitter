"""Reproducible figure + macro pipeline for book Chapter 8 (the clock).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch08\\gen_figures.py
    ... gen_figures.py --only fig_clk_read         # one figure
    ... gen_figures.py --list                      # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
(ATM ladders only -- no smile is refitted) and the deterministic synthetic
constructions of appendix 8.A.  The only randomness is the fixed-seed walk
of fig_clk_walk.
Outputs: ``figures/ch08/fig_*.pdf``, ``figures/ch08/ch08_macros.tex`` (every
number the chapter quotes), ``figures/ch08/MACROS.md``.  Fully deterministic.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).resolve().parent / "figlib"))

import figstyle  # noqa: E402

figstyle.setup()

import fig_board  # noqa: E402
import fig_clock  # noqa: E402
import fig_crush  # noqa: E402
import fig_ident  # noqa: E402
import fig_interp  # noqa: E402
import fig_read  # noqa: E402
import fig_walk  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F7.
FIGURES = {
    "fig_clk_board": fig_board.fig_clk_board,
    "fig_clk_walk": fig_walk.fig_clk_walk,
    "fig_clk_clock": fig_clock.fig_clk_clock,
    "fig_clk_crush": fig_crush.fig_clk_crush,
    "fig_clk_interp": fig_interp.fig_clk_interp,
    "fig_clk_ident": fig_ident.fig_clk_ident,
    "fig_clk_read": fig_read.fig_clk_read,
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
