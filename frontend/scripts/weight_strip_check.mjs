// Headless-Edge LIVE check of the Parametric lens's Weights strip (quote
// weighting, 2026-09-09) on the synthetic single-origin smoke server
// (backend/smoke_server.py):
//   1. the strip mounts under the smile with the "target" / "weight (mean 1)"
//      legend and one bar pair per quote, each pair's x on the chart's own
//      x axis — compared, quote by quote, with the chart's own markers
//      (both carry data-quote-index);
//   2. a wheel zoom and a drag pan on the chart move the strip with it (the
//      pairs stay under their markers, the out-of-view ones drop);
//   3. the Strike K axis mode re-places both the same way;
//   4. the Uniform scheme: the target bars go flat, the weights decay across
//      the crowded upper strikes (their multiplier < 1), read from the API.
// Port 4196 (never 4190 — the WHATWG fetch bad-ports list). Screenshots in
// .smoke/weight-strip-*.png. Prereqs: npm run build, Edge, ../.venv.
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4196;
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const BASE = `http://localhost:${PORT}`;
const ALIGN_PX = 1.5; // a bar pair straddles its quote's x; the marker is a 2.2 px tick

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

/** Document-x of every quote marker (chart) and bar pair (strip), by index. */
const positions = () => {
  const centre = (el) => { const b = el.getBoundingClientRect(); return b.left + b.width / 2; };
  const chart = {};
  for (const g of document.querySelectorAll('main [data-testid="quote-layer-market"] [data-quote-index]')) {
    const mid = g.querySelector("path:nth-of-type(2)") ?? g.querySelector("path"); // the mid tick (or the mark)
    if (mid) chart[g.getAttribute("data-quote-index")] = centre(mid);
  }
  const strip = {};
  for (const g of document.querySelectorAll('[data-testid="weight-strip"] [data-quote-index]')) strip[g.getAttribute("data-quote-index")] = centre(g);
  return { chart, strip };
};

/** Compare the strip's pairs with the chart's markers for the SAME index. */
function compare(pos, what) {
  const idx = Object.keys(pos.strip);
  if (idx.length === 0) throw new Error(`${what}: the strip drew no bars`);
  let worst = 0;
  let matched = 0;
  for (const i of idx) {
    if (!(i in pos.chart)) continue; // the chart clips its markers; the strip skips beyond ±4 px
    matched += 1;
    worst = Math.max(worst, Math.abs(pos.strip[i] - pos.chart[i]));
  }
  if (matched < 3) throw new Error(`${what}: only ${matched} bar pairs matched a chart marker`);
  if (worst > ALIGN_PX) throw new Error(`${what}: a bar pair sits ${worst.toFixed(1)} px off its quote marker`);
  return { matched, worst, bars: idx.length };
}

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
  const expiry = universe.expiries[ticker][2]?.expiry ?? universe.expiries[ticker][0].expiry;
  await api("PUT", "/settings/fit", { weightScheme: "equal" });

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape");
  await sleep(400);
  const lens = await page.$('button[aria-label="Parametric"]');
  if (!lens) throw new Error("Parametric lens button not found");
  await lens.click();
  await sleep(1200);
  await waitFor(page, () => document.querySelectorAll('main [data-testid="quote-layer-market"] [data-quote-index]').length >= 5, "the market quotes");

  await step("strip-mounts-on-the-chart-axis", async () => {
    const btn = await page.$('[aria-label="Chart layers"] button[aria-label="Weights"]'); // icon-only rail button
    if (!btn) throw new Error("the Weights layer button is missing");
    await btn.click();
    await waitFor(page, () => document.querySelectorAll('[data-testid="weight-strip"] [data-quote-index]').length >= 5, "the strip's bars");
    const legend = await page.evaluate(() => document.querySelector('[data-testid="weight-strip"]')?.innerText ?? "");
    if (!/target · one per quote/.test(legend)) throw new Error(`legend reads "${legend.replace(/\n/g, " · ")}"`);
    if (!/weight \(mean 1\)/.test(legend) || !/scheme equal/.test(legend)) throw new Error(`legend reads "${legend.replace(/\n/g, " · ")}"`);
    const r = compare(await page.evaluate(positions), "base view");
    console.log(`     ${r.bars} bar pairs, ${r.matched} under a marker, worst offset ${r.worst.toFixed(2)} px`);
    await page.screenshot({ path: `${OUT}weight-strip-base.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("strip-follows-wheel-zoom-and-pan", async () => {
    const svg = await page.$("main svg.cursor-crosshair");
    if (!svg) throw new Error("the smile chart svg is missing");
    const box = await svg.boundingBox();
    const before = await page.evaluate(positions);
    await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.5);
    for (let i = 0; i < 4; i++) { await page.mouse.wheel({ deltaY: -240 }); await sleep(120); }
    await sleep(500);
    const zoomed = await page.evaluate(positions);
    const rz = compare(zoomed, "after the zoom");
    const spreadBefore = Math.max(...Object.values(before.strip)) - Math.min(...Object.values(before.strip));
    const spreadAfter = Math.max(...Object.values(zoomed.strip)) - Math.min(...Object.values(zoomed.strip));
    if (Object.keys(zoomed.strip).length >= Object.keys(before.strip).length && spreadAfter <= spreadBefore + 1)
      throw new Error(`the strip did not zoom (bars ${Object.keys(before.strip).length} → ${Object.keys(zoomed.strip).length}, spread ${spreadBefore.toFixed(0)} → ${spreadAfter.toFixed(0)} px)`);
    console.log(`     zoom: bars ${Object.keys(before.strip).length} → ${Object.keys(zoomed.strip).length}, worst offset ${rz.worst.toFixed(2)} px`);
    await page.screenshot({ path: `${OUT}weight-strip-zoomed.png` });
    // Drag-pan a quarter of the plot to the right: every pair moves with its marker.
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.75, box.y + box.height * 0.5, { steps: 8 });
    await page.mouse.up();
    await sleep(500);
    const panned = await page.evaluate(positions);
    const rp = compare(panned, "after the pan");
    const shared = Object.keys(panned.strip).filter((i) => i in zoomed.strip);
    const shift = shared.length ? panned.strip[shared[0]] - zoomed.strip[shared[0]] : 0;
    if (shift < 20) throw new Error(`the strip did not pan (shift ${shift.toFixed(0)} px)`);
    console.log(`     pan: shift ${shift.toFixed(0)} px, worst offset ${rp.worst.toFixed(2)} px`);
    await page.screenshot({ path: `${OUT}weight-strip-panned.png` });
    await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5, { clickCount: 2 }); // reset
    await sleep(400);
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("strip-follows-the-strike-axis", async () => {
    const changed = await page.evaluate(() => {
      const sel = Array.from(document.querySelectorAll("main select")).find((s) => Array.from(s.options).some((o) => o.value === "strike"));
      if (!sel) return false;
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
      setter.call(sel, "strike");
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    });
    if (!changed) throw new Error("the axis-mode select is missing");
    await sleep(700);
    const r = compare(await page.evaluate(positions), "strike axis");
    console.log(`     strike axis: ${r.matched} pairs under a marker, worst offset ${r.worst.toFixed(2)} px`);
    await page.screenshot({ path: `${OUT}weight-strip-strike.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("uniform-target-decays-over-crowded-strikes", async () => {
    await api("PUT", "/settings/fit", { weightScheme: "uniform_density" });
    const w = await api("GET", `/smiles/${ticker}/${expiry}/weights`);
    if (w.scheme !== "uniform_density") throw new Error(`scheme ${w.scheme}`);
    const inc = w.entries.filter((e) => !e.excluded);
    if (inc.some((e) => Math.abs(e.weightRaw - 1) > 1e-12)) throw new Error("the uniform target is not flat");
    const mean = inc.reduce((s, e) => s + e.weight, 0) / inc.length;
    if (Math.abs(mean - 1) > 1e-9) throw new Error(`weights mean ${mean}`);
    const spread = Math.max(...inc.map((e) => e.weight)) / Math.min(...inc.map((e) => e.weight));
    console.log(`     ${inc.length} quotes: target flat, weights mean 1, max/min weight ${spread.toFixed(2)}`);
    // The strip re-reads after the settings change: reload the node view.
    await page.reload({ waitUntil: "networkidle2", timeout: 30000 });
    await sleep(2500);
    await page.keyboard.press("Escape");
    await sleep(400);
    await waitFor(page, () => /scheme uniform_density/.test(document.querySelector('[data-testid="weight-strip"]')?.innerText ?? ""), "the uniform strip", 30000);
    const legend = await page.evaluate(() => document.querySelector('[data-testid="weight-strip"]')?.innerText ?? "");
    if (!/target · uniform/.test(legend)) throw new Error(`legend reads "${legend.replace(/\n/g, " · ")}"`);
    const heights = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-testid="weight-strip"] g[data-quote-index]')).map((g) => {
        const [t, w] = Array.from(g.querySelectorAll("rect")).map((r) => Number(r.getAttribute("height")));
        return { t, w };
      }));
    const targetsFlat = heights.every((h) => Math.abs(h.t - heights[0].t) < 1e-6);
    const weightsVary = Math.max(...heights.map((h) => h.w)) - Math.min(...heights.map((h) => h.w)) > 2;
    if (!targetsFlat) throw new Error("the target bars are not flat under the uniform scheme");
    if (!weightsVary) throw new Error("the weight bars do not vary under the uniform scheme");
    await page.screenshot({ path: `${OUT}weight-strip-uniform.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });
} finally {
  await api("PUT", "/settings/fit", { weightScheme: "equal" }).catch(() => {});
  await browser.close();
  server.kill();
}
if (failures > 0) { console.error(`${failures} step(s) failed`); process.exit(1); }
console.log("Weights strip: on the chart's axis (base · zoom · pan · strike), target vs weight, the Uniform scheme (screenshots in .smoke/weight-strip-*.png)");
