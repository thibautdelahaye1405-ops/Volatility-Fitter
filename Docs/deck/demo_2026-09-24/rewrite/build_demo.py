"""Build the technical demo deck and its synchronized speaker notes from the
chapter JSON files (01_inputs.json … 05_graph_and_use.json).

Presentation layer (2026-09-29): the capabilities deck's design system —
kicker / claim / lede, formula blocks on the left, evidence on the right, the
"illustrative calculation" as an accent strip, captions with a bold lead — and
LaTeX equations rendered offline with latex + dvisvgm (glyphs as paths, coloured
by CSS), cached under assets/eq_demo/gen by the hash of the TeX. Matplotlib
mathtext is only the fallback when LaTeX rejects a formula.

Inline maths: any slide-visible prose field (lede, bullets, example, table cells,
captions, demo cues) may carry ``$...$`` spans; they are rendered through the
same LaTeX pipeline in text style, sized to the surrounding font and sat on the
text baseline. Titles stay plain text.

Layouts: default (formula + bullets | figure or table), ``cover`` (title slide),
``close`` (closing slide), ``wide-image``, ``narrow-image`` (a portrait capture
beside a wide table), ``half-image`` (formulas and figure at equal width),
``compact``.

Formula blocks: ``eq_labels`` (optional, aligned with ``eq``) puts a small label
above each display — a step name, so the block reads as a sequence.

Speaker notes: a note paragraph that opens with a cue label — "If asked …:" or
"Transition:" — gets that label in bold, in the overlay and in the Markdown.

Run with the repository venv Python (MiKTeX's latex / dvisvgm on PATH):
    .venv\\Scripts\\python.exe Docs\\deck\\demo_2026-09-24\\rewrite\\build_demo.py
The existing deck builder (Docs/deck/build.py) then inlines the archived
screenshots ({{SHOT:}}) and reference-note figures ({{FIG:}}).
"""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECK = HERE.parents[1]
sys.path.insert(0, str(DECK))
from build import _svg_body  # noqa: E402  (the deck builder's SVG inliner)

#: pt -> px for the display formulas (the capabilities deck uses 2.3; these slides
#: carry one or two short displays each, so they can afford a little more).
EQ_SCALE = 2.7
#: pt -> px for inline maths, per CSS pixel of the surrounding font: LaTeX's 10 pt
#: x-height (≈ 4.3 pt) matched to Segoe UI's (≈ 0.5 em) gives ≈ 0.116 px/pt per px.
INLINE_SCALE_PER_PX = 0.116
EQ_CACHE = DECK / "assets" / "eq_demo" / "gen"
EQ_CACHE.mkdir(parents=True, exist_ok=True)
SHOTS = DECK / "assets" / "shots_demo"
PLOTS = DECK / "assets" / "plots_demo"

LATEX_PRE = r"""\documentclass[preview,border=3pt]{standalone}
\usepackage{amsmath,amssymb}
\newcommand{\clip}{\operatorname{clip}}
\begin{document}
"""
LATEX_POST = "\n\\end{document}\n"


# ------------------------------------------------------------------ equations
def _normalise_tex(tex: str) -> str:
    """The JSON formulas were written for matplotlib mathtext; real LaTeX takes
    them as they are, apart from a handful of spellings."""
    return re.sub(r"\\(mathcal|mathbb)\s+([A-Za-z])", r"\\\1{\2}", tex)


def latex_svg(tex: str, display: bool = True) -> Path | None:
    """Render one formula to an SVG file (cached by content hash); None when
    latex / dvisvgm fail. ``display`` = \\displaystyle (the formula blocks),
    otherwise text style (inline maths inside prose)."""
    body = (r"\mbox{$\displaystyle " if display else r"\mbox{$") + _normalise_tex(tex) + "$}"
    key = hashlib.sha1(body.encode("utf-8")).hexdigest()[:14]
    out = EQ_CACHE / f"{key}.svg"
    if out.exists():
        return out
    work = EQ_CACHE / "_work"
    work.mkdir(exist_ok=True)
    (work / f"{key}.tex").write_text(LATEX_PRE + body + LATEX_POST, encoding="utf-8")
    try:
        r = subprocess.run(["latex", "-interaction=nonstopmode", "-halt-on-error", f"{key}.tex"],
                           cwd=work, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return None
        r = subprocess.run(["dvisvgm", "-n", "-e", f"{key}.dvi", "-o", f"{key}.svg"],
                           cwd=work, capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not (work / f"{key}.svg").exists():
            return None
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (work / f"{key}.svg").read_text(encoding="utf-8")
    text = text.replace("<svg version=", "<svg fill='currentColor' version=", 1)
    out.write_text(text, encoding="utf-8")
    return out


def mathtext_fallback(tex: str, inline: bool = False) -> str:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import mathtext
    from matplotlib.font_manager import FontProperties

    buf = io.BytesIO()
    rendered = tex.replace(r"\bigg|", "|")
    rendered = re.sub(r"\\frac(\d)(\d)", r"\\frac{\1}{\2}", rendered)
    rendered = re.sub(r"\\(mathcal|mathbb)\s+([A-Za-z])", r"\\\1{\2}", rendered)
    mathtext.math_to_image("$" + rendered + "$", buf, format="svg", dpi=160, color="#0B1520",
                           prop=FontProperties(size=14 if inline else 30, math_fontfamily="stix"))
    uri = "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
    cls = "equation-inline" if inline else "equation"
    return f'<img class="{cls}" src="{uri}" alt="{html.escape(tex, quote=True)}">'


def equation(tex: str) -> str:
    path = latex_svg(tex, display=True)
    if path is None:
        print(f"WARNING latex rejected: {tex[:60]} — mathtext fallback")
        return mathtext_fallback(tex)
    return _svg_body(path, scale=EQ_SCALE, ns=f"eqg-{path.stem}")


def inline_math(tex: str, px: float) -> str:
    """One ``$...$`` span: text-style LaTeX scaled to the surrounding font and
    sat on its baseline (dvisvgm's viewBox puts the baseline at y = 0, so the
    depth below it is height + min-y)."""
    path = latex_svg(tex, display=False)
    if path is None:
        print(f"WARNING latex rejected inline: {tex[:60]} — mathtext fallback")
        return mathtext_fallback(tex, inline=True)
    scale = INLINE_SCALE_PER_PX * px
    svg = _svg_body(path, scale=scale, ns=f"im-{path.stem}-{int(px * 10)}")
    m = re.search(r"viewBox='([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)'", svg)
    depth_px = (float(m.group(4)) + float(m.group(2))) * scale if m else 0.0
    svg = svg.replace("<svg ", f"<svg style='vertical-align:{-depth_px:.1f}px' ", 1)
    return f'<span class="im">{svg}</span>'


def rich(text: str, px: float = 21.0) -> str:
    """Escape prose and render its ``$...$`` spans as inline maths; ``\\$`` is a
    literal dollar sign (a currency amount), never a maths delimiter."""
    text = text.replace("\\$", "\x00")
    parts = re.split(r"(\$[^$]+\$)", text)
    out = []
    for part in parts:
        if len(part) > 2 and part.startswith("$") and part.endswith("$"):
            out.append(inline_math(part[1:-1], px))
        else:
            out.append(html.escape(part))
    return "".join(out).replace("\x00", "$")


# ---------------------------------------------------------------- fragments
esc = html.escape
PX_POINTS, PX_LEDE, PX_TABLE, PX_STRIP, PX_CAP, PX_DEMO = 21.0, 22.5, 20.0, 20.5, 17.0, 16.5


def render_eqs(s: dict) -> str:
    eqs = s.get("eq") or []
    if not eqs:
        return ""
    title = f'<div class="eqtitle">{rich(s["eq_title"], 15)}</div>' if s.get("eq_title") else ""
    labels = s.get("eq_labels") or []
    rows = ""
    for i, e in enumerate(eqs):
        label = labels[i] if i < len(labels) else ""
        if label:
            rows += f'<div class="eq labelled"><span class="eqlbl">{rich(label, 14)}</span>{equation(e)}</div>'
        else:
            rows += f'<div class="eq">{equation(e)}</div>'
    note = f'<div class="eqnote">{rich(s["eq_note"], 14.5)}</div>' if s.get("eq_note") else ""
    return f'<div class="eqblock core">{title}{rows}{note}</div>'


def render_points(s: dict, px: float = PX_POINTS) -> str:
    paras = s.get("paras") or []
    if not paras:
        return ""
    items = "".join(f"<li><strong>{rich(p[0], px)}:</strong> {rich(p[1], px)}</li>" for p in paras)
    return f'<ul class="points">{items}</ul>'


def render_table(s: dict) -> str:
    data = s.get("table")
    if not data:
        return ""
    head = "".join(f"<th>{rich(str(x), 15)}</th>" for x in data["head"])
    rows = "".join("<tr>" + "".join(f"<td>{rich(str(x), PX_TABLE)}</td>" for x in row) + "</tr>"
                   for row in data["rows"])
    return f'<div class="tablecard"><table class="grid"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def render_example(s: dict) -> str:
    if not s.get("example"):
        return ""
    label = s.get("example_label", "Illustrative calculation")
    tone = " amber" if re.search(r"recorded|measured|limitation", label, re.I) else ""
    return f'<div class="strip{tone}"><span class="lbl">{esc(label)}</span>{rich(s["example"], PX_STRIP)}</div>'


def render_demo(s: dict) -> str:
    if not s.get("demo"):
        return ""
    return f'<div class="demo"><span class="lbl">In the app</span><span>{rich(s["demo"], PX_DEMO)}</span></div>'


def caption(text: str) -> str:
    """Bold lead up to the first ':' or '. ' — the capabilities deck's caption style."""
    m = re.match(r"^(.{8,90}?[:.])\s+(.*)$", text, re.S)
    if m and "$" not in m.group(1):
        return f'<p class="shotcap"><span class="k">{esc(m.group(1))}</span> {rich(m.group(2), PX_CAP)}</p>'
    return f'<p class="shotcap">{rich(text, PX_CAP)}</p>'


def _aspect(name: str) -> float | None:
    try:
        from PIL import Image
        with Image.open(SHOTS / f"{name}.png") as im:
            w, h = im.size
        return w / h
    except Exception:  # noqa: BLE001 — PIL missing / file missing
        return None


def _shot_class(name: str) -> str:
    """A 1600x1000 (@2x) app capture carries the status bar at the bottom (hide
    it); a portrait or square crop sits in a fixed-height panel (object-fit)."""
    a = _aspect(name)
    if a is None:
        return "shot"
    if abs(a - 1.6) < 0.02:
        return "shot nosb"
    if a < 1.35:
        return "shot fit"
    return "shot"


def render_figure(s: dict) -> str:
    if s.get("image"):
        kind, name = s["image"].split(":", 1)
        src = "{{" + s["image"] + "}}"
        if kind == "SHOT":
            cls = _shot_class(name)
            return f'<div class="{cls}"><img src="{src}" alt="{esc(s["alt"], quote=True)}"></div>' + caption(s["caption"])
        return f'<div class="figcard"><img src="{src}" alt="{esc(s["alt"], quote=True)}"></div>' + caption(s["caption"])
    if s.get("plot"):
        path = PLOTS / (s["plot"] + ".svg")
        src = "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()
        return f'<div class="figcard plot"><img src="{src}" alt="{esc(s["alt"], quote=True)}"></div>' + caption(s["caption"])
    return ""


# ------------------------------------------------------------------- slides
#: A speaker-note paragraph that opens with one of these cue labels gets it in bold.
NOTE_CUE = re.compile(r"^((?:If asked[^:]{0,90})|Transition):\s+")


def note_html(p: str) -> str:
    m = NOTE_CUE.match(p)
    if not m:
        return f"<p>{esc(p)}</p>"
    return f"<p><b>{esc(m.group(1))}:</b> {esc(p[m.end():])}</p>"


def note_md(p: str) -> str:
    m = NOTE_CUE.match(p)
    return f"**{m.group(1)}:** {p[m.end():]}" if m else p


def render_notes(s: dict, index: int) -> str:
    notes = "".join(note_html(p) for p in s["notes"])
    if s.get("demo"):
        notes += f"<p><b>In the app.</b> {esc(s['demo'])}</p>"
    return f'<aside class="notes" aria-label="Speaker notes"><h2>{index:02d} · {esc(s["title"])}</h2>{notes}</aside>'


def render_cover(s: dict, total: int) -> str:
    cards = "".join(f'<div class="it"><b>{esc(p[0])}</b>{rich(p[1], 19.5)}</div>' for p in s.get("paras", []))
    return f'''<section class="slide title" id="{s['id']}" data-section="{esc(s['section'])}">
  <div class="brand">{esc(s['section'])}</div>
  <h1>{esc(s['title'])}</h1>
  <p class="sub">{rich(s['lede'], 30)}</p>
  <div class="agenda">{cards}</div>
  <div class="titleshots">
    <div class="titleshot"><span class="shotlbl">Parametric lens · live quotes and fit</span><img src="{{{{SHOT:shell_hero}}}}" alt="The workbench: Parametric lens on a live node"></div>
    <div class="titleshot"><span class="shotlbl">Graph lens · observed and inferred nodes</span><img src="{{{{SHOT:graph_canvas_run}}}}" alt="The graph lens after a Run"></div>
  </div>
  <div class="foot"><span>{esc(s['reference'])}</span><span>01 / {total:02d}</span></div>
  {render_notes(s, 1)}
</section>'''


def render_close(s: dict, index: int, total: int) -> str:
    return f'''<section class="slide close" id="{s['id']}" data-section="{esc(s['section'])}">
  <div class="brand">{esc(s['section'])}</div>
  <h1>{esc(s['title'])}</h1>
  <p class="sub">{rich(s['lede'], 27)}</p>
  {render_points(s, 22.0)}
  {render_demo(s)}
  <div class="foot"><span>{esc(s['reference'])}</span><span>{index:02d} / {total:02d}</span></div>
  {render_notes(s, index)}
</section>'''


def render_slide(s: dict, index: int, total: int, sec_pos: int, sec_total: int) -> str:
    if s.get("layout") == "cover":
        return render_cover(s, total)
    if s.get("layout") == "close":
        return render_close(s, index, total)
    eqs, points, table, example, demo, figure = (render_eqs(s), render_points(s), render_table(s),
                                                 render_example(s), render_demo(s), render_figure(s))
    compact = " compact" if s.get("layout") == "compact" else ""
    if figure:
        cols = {"wide-image": "cols wider", "narrow-image": "cols narrow",
                "half-image": "cols half"}.get(s.get("layout"), "cols")
        left = eqs + points + table + example + demo
        body = f'<div class="{cols}{compact}"><div>{left}</div><div>{figure}</div></div>'
    elif table and (eqs or points):
        body = f'<div class="cols half{compact}"><div>{eqs}{points}{demo}</div><div>{table}{example}</div></div>'
    elif eqs:
        body = f'<div class="cols half{compact}"><div>{eqs}</div><div>{points}{example}{demo}</div></div>'
    else:
        body = f'<div class="one{compact}">{points}{table}{example}{demo}</div>'
    return f'''<section class="slide" id="{s['id']}" data-section="{esc(s['section'])}">
  <div class="kicker"><span class="step">{esc(s['section'])}</span><span class="tag">{sec_pos} / {sec_total}</span></div>
  <h1 class="claim">{esc(s['title'])}</h1>
  <p class="lede">{rich(s['lede'], PX_LEDE)}</p>
  <div class="body">{body}</div>
  <div class="foot"><span>{esc(s['reference'])}</span><span>{index:02d} / {total:02d}</span></div>
  {render_notes(s, index)}
</section>'''


# -------------------------------------------------------------------- notes
def write_notes(slides: list[dict]) -> None:
    notes = ["# Vol-Fitter — speaker notes", "",
             "Internal technical presentation for quants and traders. Rewritten 28 September 2026.", "",
             "Companion: [HTML deck](demo_deck.html). The numbering and titles below match the deck. Press **N** for the notes, **O** for the contents, and use the arrow keys to navigate. The deck works offline.", "",
             "The archived app captures are dated 24 September 2026. Numerical examples labelled *illustrative* explain a mechanism; recorded measurements retain their date, inputs, and scope. Volatility is stored as a decimal: one vol point = 0.01 and one vol bp = 0.0001. Calendar time is t, the pricing variance clock is τ, normalized strike is x = K/F, and log-moneyness is k = log(K/F). Inline `$…$` spans are LaTeX, as on the slides.", "",
             "## Contents", ""]
    for i, s in enumerate(slides, 1):
        notes.append(f"- [{i:02d}. {s['title']}](#slide-{i:02d})")
    for i, s in enumerate(slides, 1):
        notes.extend(["", f'<a id="slide-{i:02d}"></a>', "", f"## {i:02d}. {s['title']}", "", f"*{s['section']}*", ""])
        notes.extend([s["lede"], ""])
        labels = s.get("eq_labels") or []
        for i, eq in enumerate(s.get("eq", [])):
            if i < len(labels) and labels[i]:
                notes.extend([f"*{labels[i]}*", ""])
            notes.extend(["$$", eq, "$$", ""])
        if s.get("table"):
            table = s["table"]
            notes.append("| " + " | ".join(table["head"]) + " |")
            notes.append("| " + " | ".join("---" for _ in table["head"]) + " |")
            notes.extend("| " + " | ".join(str(x).replace("|", r"\|") for x in row) + " |" for row in table["rows"])
            notes.append("")
        notes.extend(note_md(p) + "\n" for p in s["notes"])
        if s.get("example"):
            notes.extend([f"**{s.get('example_label', 'Illustrative calculation')}.** {s['example']}", ""])
        if s.get("image") or s.get("plot"):
            notes.extend([f"**Visual.** {s['caption']}", ""])
        if s.get("demo"):
            notes.extend([f"**In the app.** {s['demo']}", ""])
    (DECK / "demo_speaker_notes_2026-09-24.md").write_text("\n".join(notes) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- main
def main() -> None:
    slides: list[dict] = []
    for chapter in sorted(HERE.glob("[0-9][0-9]_*.json")):
        slides.extend(json.loads(chapter.read_text(encoding="utf-8")))
    ids = [s["id"] for s in slides]
    assert len(ids) == len(set(ids)), "Duplicate slide IDs"
    for s in slides:
        assert s.get("notes") and s.get("sources"), s["id"]
        for source in s["sources"]:
            assert (DECK.parents[1] / source.split("#")[0]).exists(), source
    # position of each slide inside its section (the kicker's "k / n" tag)
    sec_total: dict[str, int] = {}
    for s in slides:
        sec_total[s["section"]] = sec_total.get(s["section"], 0) + 1
    sec_seen: dict[str, int] = {}
    rendered = []
    for i, s in enumerate(slides, 1):
        sec_seen[s["section"]] = sec_seen.get(s["section"], 0) + 1
        rendered.append(render_slide(s, i, len(slides), sec_seen[s["section"]], sec_total[s["section"]]))
    shell = (HERE / "shell.html").read_text(encoding="utf-8")
    (DECK / "demo_deck_template.html").write_text(shell.replace("<!-- SLIDES -->", "\n".join(rendered)), encoding="utf-8")
    write_notes(slides)
    subprocess.run([sys.executable, str(DECK / "build.py"), str(DECK / "demo_deck_template.html"),
                    str(DECK / "demo_deck.html")], check=True)
    print(f"Built {len(slides)} slides and synchronized speaker notes.")


if __name__ == "__main__":
    main()
