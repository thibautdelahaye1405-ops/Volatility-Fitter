// "Chart as PNG" (UI SHELL v2 wave 3, A3): rasterize the active chart card's
// SVG through a canvas. The hand-rolled charts style text / grid lines with
// Tailwind classes (fill-slate-500 …) and CSS variables, which a serialized
// SVG would lose — so the clone gets every element's COMPUTED fill / stroke /
// font / opacity inlined first. Drawn at 2× device pixels on the card's
// background colour; the filename is `<ticker>_<expiry>_<view>.png`.

/** Marker attribute a lens puts on the element that wraps its chart card body. */
export const CHART_CARD_ATTR = "data-chart-card";

const STYLE_PROPS = [
  "fill", "fill-opacity", "stroke", "stroke-opacity", "stroke-width", "stroke-dasharray",
  "font-family", "font-size", "font-weight", "opacity", "color",
] as const;

/** `<ticker>_<expiry>_<view>.png` (safe characters only). */
export function chartPngFilename(ticker: string, expiry: string, view: string): string {
  const clean = (s: string) => s.replace(/[^a-zA-Z0-9.-]+/g, "-").replace(/^-+|-+$/g, "");
  return `${clean(ticker) || "chart"}_${clean(expiry) || "node"}_${clean(view) || "chart"}.png`;
}

/** The SVG of the active chart card (first svg inside the marked wrapper). */
export function findActiveChartSvg(root: ParentNode = document): SVGSVGElement | null {
  const card = root.querySelector(`[${CHART_CARD_ATTR}]`);
  return (card?.querySelector("svg") as SVGSVGElement | null) ?? null;
}

/** Deep-clone an SVG with computed presentation styles inlined as attributes. */
export function inlineSvgStyles(svg: SVGSVGElement): SVGSVGElement {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const src = svg.querySelectorAll<Element>("*");
  const dst = clone.querySelectorAll<Element>("*");
  const view = svg.ownerDocument.defaultView;
  if (view) {
    for (let i = 0; i < src.length && i < dst.length; i++) {
      const cs = view.getComputedStyle(src[i]);
      const style: string[] = [];
      for (const p of STYLE_PROPS) {
        const v = cs.getPropertyValue(p);
        if (v && v !== "none" && v !== "normal" && v !== "" && v !== "auto") style.push(`${p}:${v}`);
      }
      if (style.length) dst[i].setAttribute("style", style.join(";"));
      dst[i].removeAttribute("class");
    }
    const rootCs = view.getComputedStyle(svg);
    clone.setAttribute("style", `font-family:${rootCs.fontFamily};font-size:${rootCs.fontSize}`);
  }
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const w = svg.clientWidth || Number(svg.getAttribute("width")) || 800;
  const h = svg.clientHeight || Number(svg.getAttribute("height")) || 500;
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  return clone;
}

/** Rasterize an SVG to a PNG blob (scale = device pixels per CSS pixel). */
export function svgToPngBlob(svg: SVGSVGElement, background: string, scale = 2): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const clone = inlineSvgStyles(svg);
    const w = Number(clone.getAttribute("width"));
    const h = Number(clone.getAttribute("height"));
    const xml = new XMLSerializer().serializeToString(clone);
    const url = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }));
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(w * scale);
        canvas.height = Math.round(h * scale);
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("no 2d canvas context");
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.scale(scale, scale);
        ctx.drawImage(img, 0, 0, w, h);
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("PNG encoding failed"))), "image/png");
      } catch (err) {
        reject(err);
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("could not render the chart SVG")); };
    img.src = url;
  });
}

/** Background colour behind the chart (the card's computed background, or the
 *  page's). */
export function chartBackground(svg: SVGSVGElement): string {
  let el: Element | null = svg;
  const view = svg.ownerDocument.defaultView;
  while (el && view) {
    const bg = view.getComputedStyle(el).backgroundColor;
    if (bg && bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent") return bg;
    el = el.parentElement;
  }
  return "#0b1220";
}
