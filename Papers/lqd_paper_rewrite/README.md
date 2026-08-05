# LQD paper: parallel rewrite

`lqd_paper_rewrite.tex` is a complete, parallel rewrite of the original
manuscript in `../lqd_paper/`. The original source is not modified.

The rewrite reuses the original title, byline, notation, empirical snapshot,
generated numerical macros, bibliography database, and all fourteen graphics.
It reorganizes the material as a progressive monograph chapter, with longer
proofs, implementation details, and reproducibility material in appendices.

Compile from this directory with a standard LaTeX/BibTeX sequence:

```text
pdflatex lqd_paper_rewrite.tex
bibtex lqd_paper_rewrite
pdflatex lqd_paper_rewrite.tex
pdflatex lqd_paper_rewrite.tex
```
