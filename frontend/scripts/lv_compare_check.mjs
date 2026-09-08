// Headless-Edge LIVE check of the Local Vol lens's Compare tab (LV Dupire-twin
// arc, D3) on the synthetic single-origin smoke server (backend/smoke_server.py):
//   1. through the API: bootstrap every parametric fit and the LV fit of the
//      first ticker, and read the compare payload once (its figures are
//      printed for the wrap);
//   2. Local Vol → Compare: the chip row + score strip, the two σ²_loc sheets
//      side by side (Sheets), the diverging difference heatmap (Difference),
//      the three-curve smile with the score table (Smiles), then the Buckets
//      chip refetches the twin (the caption follows).
// Port 4194 (never 4190 — the WHATWG fetch bad-ports list). Screenshots in
// .smoke/lv-compare-*.png. Prereqs: npm run build, Edge, ../.venv.
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4194;
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

const mainText = () => document.querySelector("main")?.innerText ?? "";

async function clickMainButton(page, label) {
  const [btn] = await page.$$(`xpath/.//main//button[normalize-space()="${label}"]`);
  if (!btn) throw new Error(`button "${label}" not found in main`);
  await btn.click();
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
  const expiries = universe.expiries[ticker].map((e) => e.expiry);
  for (const e of expiries) await api("GET", `/smiles/${ticker}/${e}`);
  await api("POST", `/fit/affine/${ticker}`, {});
  const c = await api("POST", `/fit/affine/${ticker}/compare`, {});
  console.log(
    `compare ${ticker}: ${c.tNodes.length}x${c.xNodes.length} vertices · round trip ${c.roundTripBp.toFixed(1)} / ${c.roundTripMaxBp.toFixed(1)} bp` +
    ` · twin conv ${c.twinScore.convergedBp.toFixed(1)} · affine conv ${c.affineScore?.convergedBp?.toFixed(1)} · param ${c.parametricScore.rmsBp.toFixed(1)} bp` +
    ` · lattice ${c.affineLatticeMatches} · ${c.message}`,
  );

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape");
  await sleep(400);
  const lens = await page.$('button[aria-label="Local Vol"]');
  if (!lens) throw new Error("Local Vol lens button not found");
  await lens.click();
  await sleep(1200);

  await step("compare-sheets", async () => {
    await clickMainButton(page, "Compare");
    await waitFor(page, () => /round trip \d+ · \d+ bp/.test(document.querySelector("main")?.innerText ?? ""), "the score strip");
    const strip = await page.evaluate(() => (document.querySelector("main")?.innerText ?? "").match(/conv twin.*bp/)?.[0] ?? "");
    console.log(`     strip: ${strip}`);
    // Two 3D meshes (both svg.cursor-grab), the twin caption and the affine caption.
    await waitFor(page, () => document.querySelectorAll("main svg.cursor-grab").length >= 2, "the two sheets");
    const text = await page.evaluate(mainText);
    if (!text.includes("Dupire twin · smooth")) throw new Error("the twin caption is missing");
    if (!text.includes("affine sheet")) throw new Error("the affine caption is missing");
    await page.screenshot({ path: `${OUT}lv-compare-sheets.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("compare-difference", async () => {
    await clickMainButton(page, "Difference");
    await waitFor(page, () => (document.querySelector("main")?.innerText ?? "").includes("σ_loc twin − affine"), "the diverging legend");
    // The heatmap paints once its ResizeObserver has measured the card.
    await waitFor(page, () => document.querySelectorAll("main [data-chart-card] svg rect").length >= 20, "the heatmap cells");
    const legend = await page.evaluate(() => (document.querySelector("main")?.innerText ?? "").match(/[−+-]?\d+\.\d pt/g)?.slice(0, 2) ?? []);
    console.log(`     legend ends: ${legend.join(" … ")}`);
    await page.screenshot({ path: `${OUT}lv-compare-difference.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("compare-smiles", async () => {
    await clickMainButton(page, "Smiles");
    await waitFor(page, () => document.querySelectorAll('main svg path[data-overlay="Dupire twin"]').length >= 1, "the twin overlay path");
    const overlays = await page.evaluate(() => Array.from(document.querySelectorAll("main svg path[data-overlay]")).map((p) => p.getAttribute("data-overlay")));
    console.log(`     overlays: ${overlays.join(", ")}`);
    const rows = await page.evaluate(() => document.querySelectorAll("main [data-chart-card] table tbody tr").length);
    if (rows !== expiries.length) throw new Error(`score table has ${rows} rows, expected ${expiries.length}`);
    const selected = await page.evaluate(() => document.querySelectorAll('main [data-chart-card] table tbody tr[data-selected="true"]').length);
    if (selected !== 1) throw new Error(`expected one selected row, found ${selected}`);
    await page.screenshot({ path: `${OUT}lv-compare-smiles.png` });
    // Click another row: the selection moves (the node tab follows).
    const rowsEl = await page.$$("main [data-chart-card] table tbody tr");
    await rowsEl[rowsEl.length - 1].click();
    await sleep(800);
    const lastSelected = await page.evaluate(() => {
      const trs = Array.from(document.querySelectorAll("main [data-chart-card] table tbody tr"));
      return trs[trs.length - 1].getAttribute("data-selected") === "true";
    });
    if (!lastSelected) throw new Error("clicking the last row did not select it");
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("compare-buckets-chip", async () => {
    await clickMainButton(page, "Sheets");
    await clickMainButton(page, "Buckets");
    await waitFor(page, () => (document.querySelector("main")?.innerText ?? "").includes("Dupire twin · buckets"), "the buckets caption");
    await page.screenshot({ path: `${OUT}lv-compare-buckets.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });
} finally {
  await browser.close();
  server.kill();
}
if (failures > 0) { console.error(`${failures} step(s) failed`); process.exit(1); }
console.log("LV Compare tab: sheets · difference · smiles + table · buckets chip render live (screenshots in .smoke/lv-compare-*.png)");
