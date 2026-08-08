"""Reproducible figure + macro pipeline for book Chapter 6 (forwards).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch06\\gen_figures.py
    ... gen_figures.py --only fig_fwd_line       # one figure
    ... gen_figures.py --list                    # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
(raw dollar chains, node metadata, the stored LQD fit of the running node)
plus the deterministic synthetic boards of appendix 6.A (the only randomness
is the seeded generator of the identifiability experiment).
Outputs: ``figures/ch06/fig_*.pdf``, ``figures/ch06/ch06_macros.tex`` (every
number the chapter quotes), ``figures/ch06/MACROS.md``.  Fully deterministic.
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

import fig_borrow  # noqa: E402
import fig_divs  # noqa: E402
import fig_ident  # noqa: E402
import fig_lever  # noqa: E402
import fig_line  # noqa: E402
import fig_skew  # noqa: E402
import fig_trim  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F7.  fig_fwd_skew reads fig_fwd_line's stored macro
# (the naive-forward gap), so keep line before skew on full runs.
FIGURES = {
    "fig_fwd_line": fig_line.fig_fwd_line,
    "fig_fwd_ident": fig_ident.fig_fwd_ident,
    "fig_fwd_trim": fig_trim.fig_fwd_trim,
    "fig_fwd_lever": fig_lever.fig_fwd_lever,
    "fig_fwd_divs": fig_divs.fig_fwd_divs,
    "fig_fwd_skew": fig_skew.fig_fwd_skew,
    "fig_fwd_borrow": fig_borrow.fig_fwd_borrow,
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
