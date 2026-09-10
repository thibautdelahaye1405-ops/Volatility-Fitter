// Headless-Edge look at the SERIES EVIDENCE on a PREPARED store (SERIES ARC S5
// exit check): the V3.8 replay-day SPY series (25 frames, 15 min) calibrated
// under three lanes — LQD free, LQD + prior, LQD + prior + filter (active,
// calendar coupling off) — built by the lead into
// backend/backtest/results/series_evidence.sqlite. The smoke server serves that
// store (`--db`, `--tickers SPY`); the check opens the Series lens, picks the
// series, screenshots the Smile / Surface (sheets + difference) / Term / Lanes
// stages and prints the evidence table from the API — the damping (handle-path
// roughness) beside its rms cost per lane, on one screen.
// Port 4198 — NOT 4190 (the WHATWG fetch bad-ports list). Screenshots in
// .smoke/series-evidence-*.png. Prereqs: npm run build, Edge, ../.venv, the
// prepared store.
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4198;
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));
const DB = process.env.SERIES_DB || winPath(new URL("../../backend/backtest/results/series_evidence.sqlite", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const BASE = `http://localhost:${PORT}`;

if (!existsSync(PY) || !existsSync(SMOKE_SERVER)) throw new Error("the synthetic smoke server needs ../.venv");
if (!existsSync(DB)) throw new Error(`the prepared store is missing: ${DB}`);

function startLiveServer() {
  const proc = spawn(PY, [SMOKE_SERVER, "--port", String(PORT), "--db", DB, "--tickers", "SPY"], { stdio: ["ignore", "pipe", "pipe"] });
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

async function api(path) {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

async function clickAria(page, label) {
  const btn = await page.$(`button[aria-label="${label}"]`);
  if (!btn) throw new Error(`button[aria-label="${label}"] not found`);
  await btn.click();
  await sleep(500);
}

async function waitFor(page, fn, what, ms = 30000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn)) return;
    await sleep(200);
  }
  throw new Error(`timed out waiting for ${what}`);
}

const server = await startLiveServer();
mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
let failures = 0;
const step = async (name, fn) => {
  try { await fn(); console.log(`ok   ${name}`); } catch (err) { failures += 1; console.error(`FAIL ${name}: ${err.message}`); }
};

try {
  const list = (await api("/series?ticker=SPY")).series;
  if (!list.length) throw new Error("the prepared store holds no SPY series");
  const sid = list[0].id;
  const doc = await api(`/series/${sid}`);
  console.log(`series ${sid}: ${doc.spec.name} · ${doc.frames.length} frames · lanes ${doc.spec.lanes.map((l) => l.name).join(" | ")} · ${doc.progress.status}`);
  const evidence = await api(`/series/${sid}/evidence`);
  console.log(`evidence (expiry ${evidence.expiry}):`);
  for (const lane of doc.spec.lanes) {
    const e = evidence.lanes[lane.id];
    if (!e) continue;
    console.log(`  ${lane.name.padEnd(26)} rms ${String(e.meanRmsBp).padStart(7)} bp · max ${String(e.meanMaxIvBp).padStart(7)} bp · rough ATM ${String(e.roughnessAtmBp).padStart(7)} bp · rough skew ${String(e.roughnessSkew).padStart(7)} · |pull| ${String(e.meanAbsPullAtmBp)} bp · ζ std ${String(e.zetaAtmStd)} · fit ${String(e.meanFitMs)} ms · failed ${e.nFailed}`);
  }

  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 940 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape");
  await sleep(400);
  await clickAria(page, "Series");
  await waitFor(page, () => !!document.querySelector('[data-testid="series-transport"]'), "the transport bar");
  await waitFor(page, () => !!document.querySelector("main svg path[data-lane]"), "a lane curve", 40000);

  const stageTab = async (label) => {
    const [tab] = await page.$$(`xpath/.//main//button[normalize-space()="${label}"]`);
    if (!tab) throw new Error(`the ${label} stage tab is missing`);
    await tab.click();
    await sleep(900);
  };
  await step("evidence-smile", async () => {
    // scrub to the middle of the session
    await page.evaluate(() => {
      const input = document.querySelector('main input[aria-label="Frame"]');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(input, String(Math.floor(Number(input.max) / 2)));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await sleep(1500);
    await page.screenshot({ path: `${OUT}series-evidence-smile.png` });
  });
  await step("evidence-surface", async () => {
    await stageTab("Surface");
    await waitFor(page, () => document.querySelectorAll('[data-testid="series-surface-sheet"]').length >= 2, "surface sheets");
    await page.screenshot({ path: `${OUT}series-evidence-surface.png` });
    const [diff] = await page.$$('xpath/.//main//button[normalize-space()="Difference"]');
    if (diff) { await diff.click(); await sleep(1200); await page.screenshot({ path: `${OUT}series-evidence-surface-diff.png` }); }
  });
  await step("evidence-term", async () => {
    await stageTab("Term");
    await waitFor(page, () => !!document.querySelector('[data-testid="series-term-stage"] path[data-lane]'), "a lane on the term chart");
    await page.screenshot({ path: `${OUT}series-evidence-term.png` });
  });
  await step("evidence-lanes", async () => {
    await stageTab("Lanes");
    await waitFor(page, () => document.querySelectorAll("main table tbody tr").length >= 3, "the three lane rows");
    await sleep(1500);
    await page.screenshot({ path: `${OUT}series-evidence-lanes.png` });
  });
  if (pageErrors.length) { failures += 1; console.error(`page errors: ${pageErrors.join(" | ")}`); }
} finally {
  await browser.close();
  server.kill();
}
console.log(failures ? `${failures} check(s) FAILED` : "series evidence check: all green");
process.exit(failures ? 1 : 0);
