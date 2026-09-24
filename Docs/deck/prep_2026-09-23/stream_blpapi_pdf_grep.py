"""Grep the BLPAPI Core Developer Guide PDF (saved by WebFetch) for the
subscription 'interval' option, //blp/mktlist chains, subscription limits and
delayed-stream flags; prints the surrounding sentences with page numbers."""
import re, sys, glob
import fitz  # PyMuPDF
paths = glob.glob(r"C:\Users\thiba\.claude\projects\C--Users-thiba-vol-fitter\0ef9af5b-a4c3-41f0-8ed3-6de25054807b\tool-results\webfetch-*.pdf")
print("pdf:", paths)
doc = fitz.open(paths[0]); print("pages:", doc.page_count)
pats = {
    "interval": r"[^.\n]*\binterval\b[^.\n]*\.",
    "mktlist": r"[^.\n]*mktlist[^.\n]*\.",
    "chain": r"[^.\n]*\bchain\b[^.\n]*\.",
    "limit": r"[^.\n]*\b(limit|maximum number of subscriptions|3500|3,500)\b[^.\n]*\.",
    "delayed": r"[^.\n]*\b(delayed|IS_DELAYED_STREAM)\b[^.\n]*\.",
    "bpipe": r"[^.\n]*(B-PIPE|Server API|SAPI|Desktop API)[^.\n]*\.",
}
hits = {k: [] for k in pats}
for i, page in enumerate(doc):
    text = page.get_text()
    for k, p in pats.items():
        for m in re.finditer(p, text, flags=re.I):
            s = " ".join(m.group(0).split())
            if 30 < len(s) < 400:
                hits[k].append((i + 1, s))
for k, lst in hits.items():
    print(f"\n### {k}: {len(lst)} hits")
    seen = set()
    for pg, s in lst[:14]:
        if s in seen: continue
        seen.add(s); print(f"  p{pg}: {s}")
