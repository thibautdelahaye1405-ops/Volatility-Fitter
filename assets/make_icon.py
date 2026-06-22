"""Generate the VolFitter app icon — a volatility smile on a dark tile.

Reproducible: re-run to regenerate the committed artifacts.

    .venv\\Scripts\\python assets\\make_icon.py

Writes:
  * assets/volfitter.ico        — multi-size Windows icon (exe + pywebview window)
  * frontend/public/favicon.ico — browser-tab / WebView2 favicon (Vite copies
                                  public/ to dist/ root)

Drawn at 4x supersampling then downsampled so the curve stays crisp at 16px.
On-brand: the app's dark navy ground (#0b1220) with a sky-cyan smile (#38bdf8)
and a few "quote" dots along it.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SS = 4               # supersampling factor
SIZE = 256 * SS      # working canvas
BG = (11, 18, 32, 255)        # #0b1220  app dark ground
BG_EDGE = (17, 27, 46, 255)   # #111b2e  subtle inner panel
CURVE = (56, 189, 248, 255)   # #38bdf8  sky-400
DOT = (224, 242, 254, 255)    # #e0f2fe  near-white quote points

#: Icon sizes packed into the .ico (Windows picks the right one per context).
ICO_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def _rounded_tile(draw: ImageDraw.ImageDraw) -> None:
    """Dark rounded-square tile with a slightly lighter inset panel."""
    r = int(SIZE * 0.22)
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=r, fill=BG)
    m = int(SIZE * 0.085)
    draw.rounded_rectangle(
        [m, m, SIZE - 1 - m, SIZE - 1 - m], radius=int(r * 0.7), fill=BG_EDGE
    )


def _smile_points() -> list[tuple[float, float]]:
    """Sampled points of the convex volatility-smile parabola (in canvas px)."""
    left, right = SIZE * 0.24, SIZE * 0.76
    cx = SIZE * 0.5
    y_bottom = SIZE * 0.62   # smile minimum (ATM)
    y_top = SIZE * 0.34      # wing height
    a = (y_top - y_bottom) / ((left - cx) ** 2)
    pts = []
    n = 64
    for i in range(n + 1):
        x = left + (right - left) * i / n
        y = a * (x - cx) ** 2 + y_bottom
        pts.append((x, y))
    return pts


def render() -> Image.Image:
    """Render the full-resolution RGBA icon."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _rounded_tile(draw)

    pts = _smile_points()
    draw.line(pts, fill=CURVE, width=int(SIZE * 0.055), joint="curve")

    # Quote dots along the smile (wings + ATM).
    rdot = int(SIZE * 0.038)
    for idx in (0, len(pts) // 4, len(pts) // 2, 3 * len(pts) // 4, len(pts) - 1):
        x, y = pts[idx]
        draw.ellipse([x - rdot, y - rdot, x + rdot, y + rdot], fill=DOT)

    return img.resize((256, 256), Image.LANCZOS)


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    icon = render()

    ico_path = repo / "assets" / "volfitter.ico"
    icon.save(ico_path, sizes=ICO_SIZES)

    favicon_dir = repo / "frontend" / "public"
    favicon_dir.mkdir(parents=True, exist_ok=True)
    icon.save(favicon_dir / "favicon.ico", sizes=ICO_SIZES)

    print(f"wrote {ico_path}")
    print(f"wrote {favicon_dir / 'favicon.ico'}")


if __name__ == "__main__":
    main()
