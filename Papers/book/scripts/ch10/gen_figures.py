"""Reproducible figure + macro pipeline for book Chapter 10 (inference).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch10\\gen_figures.py
    ... gen_figures.py --only fig_flt_flat          # one figure
    ... gen_figures.py --list                       # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
(the thinned-morning ensemble refits its canonical SPY node under Chapter
3's protocol) plus deterministic synthetic constructions; the seeded
walk in fig_audit.py is the chapter's only randomness.
Outputs: ``figures/ch10/fig_*.pdf``, ``figures/ch10/ch10_macros.tex`` (every
number the chapter quotes), ``figures/ch10/MACROS.md``.
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

import fig_audit  # noqa: E402
import fig_basket  # noqa: E402
import fig_covar  # noqa: E402
import fig_flat  # noqa: E402
import fig_gate  # noqa: E402
import fig_jump  # noqa: E402
import fig_update  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F7.
FIGURES = {
    "fig_flt_flat": fig_flat.fig_flt_flat,
    "fig_flt_gate": fig_gate.fig_flt_gate,
    "fig_flt_basket": fig_basket.fig_flt_basket,
    "fig_flt_jump": fig_jump.fig_flt_jump,
    "fig_flt_update": fig_update.fig_flt_update,
    "fig_flt_covar": fig_covar.fig_flt_covar,
    "fig_flt_audit": fig_audit.fig_flt_audit,
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
