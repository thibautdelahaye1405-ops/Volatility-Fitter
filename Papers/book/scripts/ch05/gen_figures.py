"""Reproducible figure + macro pipeline for book Chapter 5 (integrals & wings).

Run from anywhere with the project virtual environment:

    .venv\\Scripts\\python.exe Papers\\book\\scripts\\ch05\\gen_figures.py
    ... gen_figures.py --only fig_vs_pins        # one figure
    ... gen_figures.py --list                    # show every target

Inputs: the frozen snapshot ``data/lqd_paper_snapshot_20260804_0208.json``
(running-node refits under Chapter 3's protocol, the stored haircut gallery
fits, and Chapter 4's whole-surface local-vol protocol) plus deterministic
constructions (no randomness anywhere).
Outputs: ``figures/ch05/fig_*.pdf``, ``figures/ch05/ch05_macros.tex`` (every
number the chapter quotes), ``figures/ch05/MACROS.md``.  Fully deterministic.
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

import fig_ceiling  # noqa: E402
import fig_envelope  # noqa: E402
import fig_limit  # noqa: E402
import fig_pins  # noqa: E402
import fig_share  # noqa: E402
import fig_term  # noqa: E402
import fig_three  # noqa: E402
from macros import STORE  # noqa: E402

# Chapter order F1..F7.
FIGURES = {
    "fig_vs_pins": fig_pins.fig_vs_pins,
    "fig_vs_three": fig_three.fig_vs_three,
    "fig_vs_share": fig_share.fig_vs_share,
    "fig_vs_ceiling": fig_ceiling.fig_vs_ceiling,
    "fig_vs_envelope": fig_envelope.fig_vs_envelope,
    "fig_wing_limit": fig_limit.fig_wing_limit,
    "fig_vs_term": fig_term.fig_vs_term,
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
