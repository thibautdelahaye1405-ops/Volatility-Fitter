// Headless-Edge LIVE check of the 3D surfaces' (k, T) crop + centred zoom
// (2026-09-08, user request) on the synthetic single-origin smoke server:
//   1. Parametric → Surface: the two brushes are there (a vertical maturity
//      brush beside the plot, the strike brush below); dragging the lower
//      maturity handle up crops the sheet (the corner label follows) and the
//      cropped sheet sits centred; ten wheel notches at an off-centre point
//      zoom in without the sheet's centre leaving the middle of the window;
//      a Shift-drag far off is clamped so the centre stays inside the window.
//   2. Local Vol → Compare → Sheets: both meshes carry the maturity brush and
//      the brushes are LOCKED — a drag on one crops both.
// Port 4195 (never 4190). Screenshots in .smoke/surface-crop-*.png.
// Prereqs: npm run build, Edge, ../.venv.
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4195;
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const BASE = `http://localhost:${PORT}`;

if (!existsSync(PY) || !existsSync(SMOKE_SERVER)) throw new Error("the synthetic smoke server needs ../.venv");

function startLiveServer() {
  const proc = spawn(PY, [SMOKE_SERVER, "--port", String(PORT)], { stdio: ["ignore", "pipe", "pipe"] });
  proc.stderr.on("data", (b) => { const t = String(b); if (/Error|Traceback/.test(t)) console.error(t); });
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 60000;
    proc.on("exit", (code) => reject(new Error(`smoke server exited (${code})`)));
    const probe = async () => {
      try { const r = await fetch(`${BASE}/universe`); if (r.ok) return resolve(proc); } catch { /* not up */ }
      if (Date.now() > deadline) return reject(new Error("smoke server did not start"));
      setTimeout(probe, 500);
    };
    probe();
  });
}

async function api(method, path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method, headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

async function waitFor(page, fn, what, ms = 20000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn)) return;
    await sleep(200);
  }
  throw new Error(`timed out waiting for ${what}`);
}

async function clickMainButton(page, label) {
  const [btn] = await page.$$(`xpath/.//main//button[normalize-space()="${label}"]`);
  if (!btn) throw new Error(`button "${label}" not found in main`);
  await btn.click();
}

/** The centre of everything drawn (frame + facets + labels: the svg's own
 *  bounding box) and the svg's size — the sheet's centre, which the fit puts
 *  in the middle of the window and the centred zoom keeps there. */
const frameCentre = () => {
  const svg = document.querySelector("main svg.cursor-grab");
  if (!svg) return null;
  const bb = svg.getBBox();
  const box = svg.getBoundingClientRect();
  return { cx: bb.x + bb.width / 2, cy: bb.y + bb.height / 2, w: box.width, h: box.height, left: box.left, top: box.top };
};

const server = await startLiveServer();
mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
let failures = 0;
const step = async (name, fn) => {
  try { await fn(); console.log(`ok   ${name}`); } catch (err) { failures += 1; console.error(`FAIL ${name}: ${err.message}`); }
};

try {
  const universe = await api("GET", "/universe");
  const ticker = universe.tickers[0];
  for (const e of universe.expiries[ticker]) await api("GET", `/smiles/${ticker}/${e.expiry}`);
  await api("POST", `/fit/affine/${ticker}`, {});

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape");
  await sleep(400);
  await (await page.$('button[aria-label="Parametric"]')).click();
  await sleep(800);
  await clickMainButton(page, "Surface");
  await waitFor(page, () => document.querySelector("main svg.cursor-grab") !== null, "the parametric surface");
  await sleep(500);

  await step("surface-brushes-and-crop", async () => {
    const lower = await page.$('main [aria-label="Lower maturity bound"]');
    const upper = await page.$('main [aria-label="Upper maturity bound"]');
    if (!lower || !upper) throw new Error("the maturity brush handles are missing");
    if (!(await page.$('main [aria-label="Lower strike bound"]'))) throw new Error("the strike brush is missing");
    const before = await page.evaluate(frameCentre);
    const labelsBefore = await page.evaluate(() => Array.from(document.querySelectorAll("main svg text")).map((t) => t.textContent));
    console.log(`     corner labels: ${labelsBefore.join(" · ")}`);
    // Drag the lower maturity handle half-way up its track.
    const hb = await lower.boundingBox();
    const track = await page.evaluate((el) => {
      const r = el.parentElement.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, x: r.left + r.width / 2 };
    }, lower);
    await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
    await page.mouse.down();
    await page.mouse.move(track.x, track.top + (track.bottom - track.top) * 0.5, { steps: 8 });
    await page.mouse.up();
    await sleep(400);
    const labelsAfter = await page.evaluate(() => Array.from(document.querySelectorAll("main svg text")).map((t) => t.textContent));
    console.log(`     after the crop: ${labelsAfter.join(" · ")}`);
    if (labelsAfter.join() === labelsBefore.join()) throw new Error("the corner labels did not change with the maturity crop");
    const after = await page.evaluate(frameCentre);
    // The cropped sheet is centred: the frame centroid stays near the window's middle.
    if (Math.abs(after.cx - after.w / 2) > after.w * 0.15 || Math.abs(after.cy - after.h / 2) > after.h * 0.2)
      throw new Error(`cropped sheet off-centre: (${after.cx.toFixed(0)}, ${after.cy.toFixed(0)}) in ${after.w}x${after.h}`);
    console.log(`     frame centre before (${before.cx.toFixed(0)}, ${before.cy.toFixed(0)}) → after (${after.cx.toFixed(0)}, ${after.cy.toFixed(0)}) in ${after.w.toFixed(0)}x${after.h.toFixed(0)}`);
    await page.screenshot({ path: `${OUT}surface-crop-cropped.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("surface-centred-zoom", async () => {
    const box = await page.evaluate(frameCentre);
    // Ten wheel notches at a point well off the centre: the sheet must NOT drift.
    await page.mouse.move(box.left + box.w * 0.15, box.top + box.h * 0.2);
    for (let i = 0; i < 10; i++) { await page.mouse.wheel({ deltaY: -120 }); await sleep(60); }
    await sleep(300);
    const zoomed = await page.evaluate(frameCentre);
    if (Math.abs(zoomed.cx - zoomed.w / 2) > zoomed.w * 0.15 || Math.abs(zoomed.cy - zoomed.h / 2) > zoomed.h * 0.2)
      throw new Error(`zoomed sheet escaped: centre (${zoomed.cx.toFixed(0)}, ${zoomed.cy.toFixed(0)}) in ${zoomed.w}x${zoomed.h}`);
    console.log(`     after 10 zoom notches off-centre: frame centre (${zoomed.cx.toFixed(0)}, ${zoomed.cy.toFixed(0)})`);
    await page.screenshot({ path: `${OUT}surface-crop-zoomed.png` });
    // A wild Shift-drag: the pan is clamped, the centre stays inside the window.
    await page.keyboard.down("Shift");
    await page.mouse.move(box.left + box.w / 2, box.top + box.h / 2);
    await page.mouse.down();
    await page.mouse.move(box.left + box.w / 2 + 3000, box.top + box.h / 2 + 2000, { steps: 12 });
    await page.mouse.up();
    await page.keyboard.up("Shift");
    await sleep(300);
    const cover = await page.evaluate(() => {
      const svg = document.querySelector("main svg.cursor-grab");
      const bb = svg.getBBox();
      const box = svg.getBoundingClientRect();
      const ox = Math.min(bb.x + bb.width, box.width) - Math.max(bb.x, 0);
      const oy = Math.min(bb.y + bb.height, box.height) - Math.max(bb.y, 0);
      return { fx: ox / box.width, fy: oy / box.height };
    });
    if (cover.fx < 0.2 || cover.fy < 0.2)
      throw new Error(`the pan dragged the sheet out: it covers ${(cover.fx * 100).toFixed(0)}% x ${(cover.fy * 100).toFixed(0)}% of the window`);
    console.log(`     after a wild pan the sheet still covers ${(cover.fx * 100).toFixed(0)}% x ${(cover.fy * 100).toFixed(0)}% of the window`);
    await page.screenshot({ path: `${OUT}surface-crop-panned.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("lv-compare-sheets-brushes", async () => {
    await (await page.$('button[aria-label="Local Vol"]')).click();
    await sleep(800);
    await clickMainButton(page, "Compare");
    await waitFor(page, () => document.querySelectorAll("main svg.cursor-grab").length >= 2, "the two sheets", 40000);
    const n = await page.evaluate(() => document.querySelectorAll('main [aria-label="Lower maturity bound"]').length);
    if (n !== 2) throw new Error(`expected a maturity brush on each sheet, found ${n}`);
    // The two sheets' brushes are locked: drag the FIRST sheet's lower
    // maturity handle up, the SECOND sheet's handle and corner label follow.
    const [first] = await page.$$('main [aria-label="Lower maturity bound"]');
    const hb = await first.boundingBox();
    const track = await page.evaluate((el) => {
      const r = el.parentElement.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, x: r.left + r.width / 2 };
    }, first);
    await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
    await page.mouse.down();
    await page.mouse.move(track.x, track.top + (track.bottom - track.top) * 0.6, { steps: 8 });
    await page.mouse.up();
    await sleep(400);
    const values = await page.evaluate(() =>
      Array.from(document.querySelectorAll('main [aria-label="Lower maturity bound"]')).map((h) => h.getAttribute("aria-valuenow")));
    if (values[0] === values[1] && Number(values[0]) > 0.01) console.log(`     both sheets' lower maturity bound: ${values[0]}`);
    else throw new Error(`the sheets' brushes are not locked: ${values.join(" vs ")}`);
    const tLabels = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main svg text")).map((t) => t.textContent).filter((t) => /^T /.test(t)));
    console.log(`     corner T labels on both sheets: ${tLabels.join(" · ")}`);
    // The upper bound is shared verbatim; the lower corner label is each
    // sheet's FIRST ROW inside the window (the smooth twin sample has rows
    // between the vertices, so it may start a little earlier than the sheet).
    if (tLabels.length !== 4 || tLabels[1] !== tLabels[3])
      throw new Error("the sheets' upper corner labels differ after the shared crop");
    await page.screenshot({ path: `${OUT}surface-crop-compare.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });
} finally {
  await browser.close();
  server.kill();
}
if (failures > 0) { console.error(`${failures} step(s) failed`); process.exit(1); }
console.log("3D surfaces: maturity + strike brushes, the crop re-centres, zoom stays centred, pans are clamped, the Compare sheets carry the brush (screenshots in .smoke/surface-crop-*.png)");
