"""Assemble the self-contained deck: inline screenshots (base64), equation SVGs
and chart SVGs into deck_template.html -> volfitter_deck.html.

Tokens in the template:
    {{IMG:name}}   -> data URI of assets/shots/name.png   (app screenshots)
    {{FIG:name}}   -> data URI of assets/fig/name.png     (note figures)
    {{EQ:name}}    -> inlined assets/eq/name.svg   (XML prolog stripped)
    {{CHART:name}} -> inlined assets/charts/name.svg
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

HERE = Path(__file__).parent
TEMPLATE = HERE / "deck_template.html"
OUT = HERE / "volfitter_deck.html"


#: Equation display scale: dvisvgm emits pt sizes; blow them up for the 1920px
#: canvas (max-width:100% in the deck CSS reins in the wide ones).
EQ_PT_TO_PX = 2.3


def _svg_body(path: Path, scale: float | None = None, ns: str | None = None) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<\?xml[^>]*\?>\s*", "", text).strip()
    if scale is not None:
        def _dim(m: re.Match[str]) -> str:
            return f"{m.group(1)}='{float(m.group(2)) * scale:.1f}px'"
        text = re.sub(r"(width|height)=['\"]([\d.]+)pt['\"]", _dim, text, count=2)
    if ns is not None:
        # dvisvgm reuses glyph ids (g1-67, ...) across files; inlining many SVGs
        # into one document makes <use href="#..."> resolve to ANOTHER equation's
        # defs. Namespace every id/reference so each equation is self-contained.
        text = re.sub(r"\bid=(['\"])", rf"id=\g<1>{ns}-", text)
        text = re.sub(r"href=(['\"])#", rf"href=\g<1>#{ns}-", text)
        text = re.sub(r"url\(#", f"url(#{ns}-", text)
    return text


def _img_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")

    def sub(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2)
        if kind == "IMG":
            return _img_uri(HERE / "assets" / "shots" / f"{name}.png")
        if kind == "FIG":
            return _img_uri(HERE / "assets" / "fig" / f"{name}.png")
        if kind == "EQ":
            return _svg_body(
                HERE / "assets" / "eq" / f"{name}.svg", scale=EQ_PT_TO_PX, ns=f"eq-{name}"
            )
        return _svg_body(HERE / "assets" / "charts" / f"{name}.svg")

    html = re.sub(r"\{\{(IMG|FIG|EQ|CHART):([a-z0-9_]+)\}\}", sub, html)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
