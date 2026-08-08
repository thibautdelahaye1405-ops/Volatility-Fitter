"""Reproducible figure + macro pipeline for book Chapter 11 (the graph).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch11\\gen_figures.py
    ... gen_figures.py --only fig_gr_universe       # one figure
    ... gen_figures.py --list                       # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
(the SPY and NVDA boards, via Chapter 3's loader and Chapter 9's stored
fits) plus deterministic synthetic constructions; the staged universe's
seeded scatter draw is the chapter's only randomness.
Outputs: ``figures/ch11/fig_*.pdf``, ``figures/ch11/ch11_macros.tex`` (every
number the chapter quotes), ``figures/ch11/MACROS.md``.
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

import fig_account  # noqa: E402
import fig_anchor  # noqa: E402
import fig_complete  # noqa: E402
import fig_contract  # noqa: E402
import fig_meet  # noqa: E402
import fig_story  # noqa: E402
import fig_universe  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F7.
FIGURES = {
    "fig_gr_universe": fig_universe.fig_gr_universe,
    "fig_gr_contract": fig_contract.fig_gr_contract,
    "fig_gr_meet": fig_meet.fig_gr_meet,
    "fig_gr_account": fig_account.fig_gr_account,
    "fig_gr_anchor": fig_anchor.fig_gr_anchor,
    "fig_gr_story": fig_story.fig_gr_story,
    "fig_gr_complete": fig_complete.fig_gr_complete,
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
